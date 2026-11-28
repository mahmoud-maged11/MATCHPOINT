import hashlib
import json
import os
import re

from pathlib import Path

from scrapers.config import BASE_DIR

from scrapers.storage.collection_snapshot import (
    CollectionSnapshotStore,
)

from scrapers.storage.postgres import (
    PostgresSettings,
)


class SnapshotConfigurationError(RuntimeError):
    pass


def snapshot_namespace(
    settings: PostgresSettings,
) -> str:

    if not isinstance(settings, PostgresSettings):

        raise TypeError(
            "Expected PostgresSettings"
        )

    identity = {
        "host": settings.host.strip().lower(),
        "port": settings.port,
        "database": settings.database,
    }

    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    digest = hashlib.sha256(
        b"matchpoint:snapshot-namespace:v1|"
        + encoded
    ).hexdigest()

    database_label = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        settings.database,
    )[:48]

    return f"db-{database_label}-{digest}"


def create_snapshot_store(
    *,
    settings: PostgresSettings | None = None,
) -> CollectionSnapshotStore:

    raw_key = os.getenv(
        "SNAPSHOT_ENCRYPTION_KEY"
    )

    if not raw_key:

        raise SnapshotConfigurationError(
            "SNAPSHOT_ENCRYPTION_KEY is required"
        )

    if not re.fullmatch(
        r"[0-9a-fA-F]{64}",
        raw_key,
    ):

        raise SnapshotConfigurationError(
            "Snapshot encryption key must contain "
            "64 hexadecimal characters"
        )

    key = bytes.fromhex(raw_key)

    raw_directory = os.getenv(
        "SNAPSHOT_DIRECTORY",
        ".runtime/snapshots",
    )

    if not raw_directory.strip():

        raise SnapshotConfigurationError(
            "Snapshot directory cannot be empty"
        )

    directory = Path(raw_directory)

    if not directory.is_absolute():

        directory = BASE_DIR / directory

    directory = directory.resolve()

    if settings is not None:

        directory = (
            directory / snapshot_namespace(settings)
        )

        if directory.is_symlink():

            raise SnapshotConfigurationError(
                "Snapshot namespace cannot be a symbolic link"
            )

    try:

        directory.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

    except OSError:

        raise SnapshotConfigurationError(
            "Snapshot directory initialization failed"
        ) from None

    return CollectionSnapshotStore(
        directory,
        integrity_key=key,
    )
