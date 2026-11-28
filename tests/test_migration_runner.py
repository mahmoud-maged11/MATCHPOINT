import os
import shutil

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.migration_runner import (
    DEFAULT_MIGRATIONS_DIR,
    LegacyDatabaseError,
    MigrationIntegrityError,
    MigrationRunner,
    discover_migrations,
    transactional_sql,
)


TEST_DATABASE = "matchpoint_migration_runner_test"


@pytest.fixture
def storage():
    if os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests disabled")

    storage = PostgresStorage(
        PostgresSettings.from_config(
            host="127.0.0.1",
            database=TEST_DATABASE,
        )
    )

    def reset():
        with storage.transaction() as conn:
            row = conn.execute(
                "SELECT current_database() AS name"
            ).fetchone()

            if row["name"] != TEST_DATABASE:
                raise RuntimeError("Unsafe test database")

            for schema in ("gold", "silver", "bronze"):
                conn.execute(
                    f"DROP SCHEMA IF EXISTS {schema} CASCADE"
                )

            conn.execute(
                "DROP TABLE IF EXISTS public.schema_migrations"
            )

    reset()

    try:
        yield storage
    finally:
        reset()


@pytest.fixture
def migrations_dir(tmp_path):
    directory = tmp_path / "migrations"

    shutil.copytree(
        DEFAULT_MIGRATIONS_DIR,
        directory,
    )

    return directory


def registry_exists(storage):
    with storage.transaction() as conn:
        row = conn.execute(
            """
            SELECT to_regclass(
                'public.schema_migrations'
            ) IS NOT NULL AS present
            """
        ).fetchone()

        return row["present"]


def test_discover_all_migrations():
    migrations = discover_migrations()

    assert [m.version for m in migrations] == list(
        range(1, 10)
    )

    assert all(len(m.checksum) == 64 for m in migrations)


def test_checksum_stable_across_line_endings(tmp_path):
    path = tmp_path / "001_test.sql"

    path.write_bytes(b"SELECT 1;\nSELECT 2;\n")
    first = discover_migrations(tmp_path)[0]

    path.write_bytes(b"SELECT 1;\r\nSELECT 2;\r\n")
    second = discover_migrations(tmp_path)[0]

    assert first.checksum == second.checksum


def test_duplicate_versions_rejected(tmp_path):
    (tmp_path / "001_first.sql").write_text("SELECT 1;")
    (tmp_path / "001_second.sql").write_text("SELECT 2;")

    with pytest.raises(MigrationIntegrityError):
        discover_migrations(tmp_path)


def test_missing_version_rejected(tmp_path):
    (tmp_path / "001_first.sql").write_text("SELECT 1;")
    (tmp_path / "003_third.sql").write_text("SELECT 3;")

    with pytest.raises(MigrationIntegrityError):
        discover_migrations(tmp_path)


def test_empty_migration_rejected(tmp_path):
    (tmp_path / "001_empty.sql").write_text("")

    with pytest.raises(MigrationIntegrityError):
        discover_migrations(tmp_path)


def test_invalid_filename_rejected(tmp_path):
    (tmp_path / "invalid.sql").write_text("SELECT 1;")

    with pytest.raises(MigrationIntegrityError):
        discover_migrations(tmp_path)


def test_transaction_wrapper_removed():
    sql = "-- Migration\nBEGIN;\nSELECT 1;\nCOMMIT;"

    result = transactional_sql(sql)

    assert "BEGIN;" not in result
    assert "COMMIT;" not in result
    assert "SELECT 1;" in result


def test_unbalanced_transaction_rejected():
    with pytest.raises(MigrationIntegrityError):
        transactional_sql("BEGIN;\nSELECT 1;")


def test_internal_commit_rejected():
    with pytest.raises(MigrationIntegrityError):
        transactional_sql(
            "SELECT 1;\nCOMMIT;\nSELECT 2;"
        )


def test_fresh_database_migration(storage):
    result = MigrationRunner(storage).run()

    assert result.applied == tuple(range(1, 10))
    assert result.skipped == ()

    with storage.transaction() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM public.schema_migrations
            """
        ).fetchone()

        assert row["total"] == 9

        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM information_schema.tables
            WHERE table_schema = 'bronze'
              AND table_type = 'BASE TABLE'
            """
        ).fetchone()

        assert row["total"] == 6


def test_rerun_is_idempotent(storage):
    runner = MigrationRunner(storage)

    runner.run()
    result = runner.run()

    assert result.applied == ()
    assert result.skipped == tuple(range(1, 10))


def test_modified_checksum_rejected(
    storage,
    migrations_dir,
):
    runner = MigrationRunner(
        storage,
        directory=migrations_dir,
    )

    runner.run()

    path = next(migrations_dir.glob("001_*.sql"))

    with path.open("a", encoding="utf-8") as file:
        file.write("\n-- Unexpected modification\n")

    with pytest.raises(MigrationIntegrityError):
        runner.run()


def test_renamed_migration_rejected(
    storage,
    migrations_dir,
):
    runner = MigrationRunner(
        storage,
        directory=migrations_dir,
    )

    runner.run()

    path = next(migrations_dir.glob("001_*.sql"))
    path.rename(migrations_dir / "001_renamed.sql")

    with pytest.raises(MigrationIntegrityError):
        runner.run()


def test_removed_migration_rejected(
    storage,
    migrations_dir,
):
    runner = MigrationRunner(
        storage,
        directory=migrations_dir,
    )

    runner.run()

    next(migrations_dir.glob("009_*.sql")).unlink()

    with pytest.raises(MigrationIntegrityError):
        runner.run()


def test_failed_migration_rolls_back_everything(
    storage,
    migrations_dir,
):
    path = migrations_dir / "010_invalid.sql"

    path.write_text(
        "SELECT * FROM bronze.nonexistent_table;",
        encoding="utf-8",
    )

    runner = MigrationRunner(
        storage,
        directory=migrations_dir,
    )

    with pytest.raises(psycopg.errors.UndefinedTable):
        runner.run()

    assert not registry_exists(storage)

    with storage.transaction() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM pg_namespace
            WHERE nspname IN ('bronze', 'silver', 'gold')
            """
        ).fetchone()

        assert row["total"] == 0


def test_legacy_database_protected(storage):
    with storage.transaction() as conn:
        conn.execute("CREATE SCHEMA bronze")

    with pytest.raises(LegacyDatabaseError):
        MigrationRunner(storage).run()

    assert not registry_exists(storage)

    with storage.transaction() as conn:
        row = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_namespace
                WHERE nspname = 'bronze'
            ) AS present
            """
        ).fetchone()

        assert row["present"]


def test_concurrent_migration_execution(storage):
    def execute():
        return MigrationRunner(storage).run()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(execute)
            for _ in range(2)
        ]

        results = [
            future.result(timeout=60)
            for future in futures
        ]

    assert sorted(
        len(result.applied)
        for result in results
    ) == [0, 9]

    assert sorted(
        len(result.skipped)
        for result in results
    ) == [0, 9]