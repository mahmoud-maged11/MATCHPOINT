
from dataclasses import dataclass
from datetime import datetime

import psycopg


CREATE_MIGRATION_REGISTRY = """
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version INTEGER PRIMARY KEY
        CHECK (version > 0),

    migration_name TEXT NOT NULL UNIQUE
        CHECK (BTRIM(migration_name) <> ''),

    checksum VARCHAR(64) NOT NULL
        CHECK (checksum ~ '^[0-9a-f]{64}$'),

    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    execution_time_ms BIGINT NOT NULL
        CHECK (execution_time_ms >= 0)
);
"""


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    version: int
    migration_name: str
    checksum: str
    applied_at: datetime
    execution_time_ms: int


def ensure_registry(
    connection: psycopg.Connection,
) -> None:
    connection.execute(CREATE_MIGRATION_REGISTRY)


def get_applied_migrations(
    connection: psycopg.Connection,
) -> list[AppliedMigration]:

    rows = connection.execute(
        """
        SELECT
            version,
            migration_name,
            checksum,
            applied_at,
            execution_time_ms
        FROM public.schema_migrations
        ORDER BY version;
        """
    ).fetchall()

    return [
        AppliedMigration(**row)
        for row in rows
    ]


def record_migration(
    connection: psycopg.Connection,
    *,
    version: int,
    migration_name: str,
    checksum: str,
    execution_time_ms: int,
) -> None:

    connection.execute(
        """
        INSERT INTO public.schema_migrations (
            version,
            migration_name,
            checksum,
            execution_time_ms
        )
        VALUES (%s, %s, %s, %s);
        """,
        (
            version,
            migration_name,
            checksum,
            execution_time_ms,
        ),
    )
