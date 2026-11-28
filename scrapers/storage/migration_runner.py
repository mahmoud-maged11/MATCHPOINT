import hashlib
import re
import time

from dataclasses import dataclass
from pathlib import Path

from scrapers.storage.postgres import PostgresStorage
from scrapers.storage.migration_registry import (
    ensure_registry,
    get_applied_migrations,
    record_migration,
)


MIGRATION_LOCK_ID = 710003

DEFAULT_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2]
    / "database"
    / "migrations"
)

MIGRATION_PATTERN = re.compile(
    r"^(\d{3,})_[a-zA-Z0-9_]+\.sql$"
)


class MigrationError(RuntimeError):
    pass


class MigrationIntegrityError(MigrationError):
    pass


class LegacyDatabaseError(MigrationError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    checksum: str
    sql: str


@dataclass(frozen=True, slots=True)
class MigrationResult:
    applied: tuple[int, ...]
    skipped: tuple[int, ...]


def discover_migrations(
    directory: Path = DEFAULT_MIGRATIONS_DIR,
) -> tuple[Migration, ...]:

    directory = Path(directory)

    if not directory.is_dir():
        raise MigrationError(
            "Migration directory does not exist"
        )

    migrations = []
    versions = set()

    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_PATTERN.fullmatch(path.name)

        if match is None:
            raise MigrationIntegrityError(
                f"Invalid migration filename: {path.name}"
            )

        version = int(match.group(1))

        if version < 1 or version in versions:
            raise MigrationIntegrityError(
                f"Invalid or duplicate version: {version}"
            )

        content = path.read_bytes()

        sql = content.decode("utf-8-sig")

        # Keep checksums stable across Windows and Linux.
        sql = sql.replace("\r\n", "\n").replace("\r", "\n")

        if not sql.strip():
            raise MigrationIntegrityError(
                f"Empty migration: {path.name}"
            )

        checksum = hashlib.sha256(
            sql.encode("utf-8")
        ).hexdigest()

        migrations.append(
            Migration(
                version=version,
                name=path.name,
                checksum=checksum,
                sql=sql,
            )
        )

        versions.add(version)

    migrations.sort(key=lambda item: item.version)

    if not migrations:
        raise MigrationError("No migrations found")

    expected = list(range(1, len(migrations) + 1))
    actual = [item.version for item in migrations]

    if actual != expected:
        raise MigrationIntegrityError(
            "Migration versions must be consecutive"
        )

    return tuple(migrations)



def transactional_sql(sql: str) -> str:
    lines = sql.splitlines()

    meaningful = [
        i for i, line in enumerate(lines)
        if line.strip()
        and not line.strip().startswith("--")
    ]

    if not meaningful:
        raise MigrationIntegrityError("Empty migration SQL")

    first = meaningful[0]
    last = meaningful[-1]

    has_begin = lines[first].strip().upper() == "BEGIN;"
    has_commit = lines[last].strip().upper() == "COMMIT;"

    if has_begin != has_commit:
        raise MigrationIntegrityError(
            "Unbalanced migration transaction wrapper"
        )

    if has_begin and has_commit:
        lines[first] = ""
        lines[last] = ""

    body = "\n".join(lines)

    if re.search(
        r"(?im)^\s*(?:BEGIN|COMMIT|ROLLBACK|"
        r"START\s+TRANSACTION|END|ABORT|"
        r"PREPARE\s+TRANSACTION)\s*;",
        body,
    ):
        raise MigrationIntegrityError(
            "Unexpected transaction control in migration"
        )

    return body


class MigrationRunner:

    def __init__(
        self,
        storage: PostgresStorage,
        *,
        directory: Path = DEFAULT_MIGRATIONS_DIR,
    ):
        self.storage = storage
        self.directory = Path(directory)

    @staticmethod
    def _has_existing_warehouse(connection) -> bool:
        result = connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_namespace
                WHERE nspname IN (
                    'bronze',
                    'silver',
                    'gold'
                )
            ) AS existing;
            """
        ).fetchone()

        return bool(result["existing"])

    @staticmethod
    def _validate_history(migrations, applied):
        local = {
            migration.version: migration
            for migration in migrations
        }

        applied_versions = sorted(
            migration.version
            for migration in applied
        )

        if applied_versions != list(
            range(1, len(applied_versions) + 1)
        ):
            raise MigrationIntegrityError(
                "Applied migration history contains gaps"
            )

        for recorded in applied:
            migration = local.get(recorded.version)

            if migration is None:
                raise MigrationIntegrityError(
                    f"Missing migration: {recorded.version}"
                )

            if migration.name != recorded.migration_name:
                raise MigrationIntegrityError(
                    f"Migration renamed: {recorded.version}"
                )

            if migration.checksum != recorded.checksum:
                raise MigrationIntegrityError(
                    f"Checksum mismatch: {recorded.version}"
                )

    def run(self) -> MigrationResult:

        migrations = discover_migrations(self.directory)

        applied_now = []
        skipped = []

        with self.storage.transaction() as connection:

            connection.execute(
                "SET LOCAL lock_timeout = '30s'"
            )

            connection.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (MIGRATION_LOCK_ID,),
            )

            ensure_registry(connection)

            applied = get_applied_migrations(connection)

            self._validate_history(migrations, applied)

            if not applied and self._has_existing_warehouse(
                connection
            ):
                raise LegacyDatabaseError(
                    "Existing warehouse has no migration "
                    "history. Verified baseline required."
                )

            applied_versions = {
                migration.version
                for migration in applied
            }

            for migration in migrations:

                if migration.version in applied_versions:
                    skipped.append(migration.version)
                    continue

                started = time.perf_counter()

                connection.execute(transactional_sql(migration.sql))

                duration_ms = int(
                    (time.perf_counter() - started) * 1000
                )

                record_migration(
                    connection,
                    version=migration.version,
                    migration_name=migration.name,
                    checksum=migration.checksum,
                    execution_time_ms=duration_ms,
                )

                applied_now.append(migration.version)

        return MigrationResult(
            applied=tuple(applied_now),
            skipped=tuple(skipped),
        )