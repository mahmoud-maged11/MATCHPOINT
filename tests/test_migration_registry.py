import os

import psycopg
import pytest

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.migration_registry import (
    ensure_registry,
    get_applied_migrations,
    record_migration,
)


@pytest.fixture
def db_connection():
    if os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    settings = PostgresSettings.from_config(
        host="127.0.0.1",
        database="matchpoint_ingestion_test",
    )

    storage = PostgresStorage(settings)
    connection = storage.connect()

    try:
        result = connection.execute(
            "SELECT current_database() AS database"
        ).fetchone()

        if result["database"] != "matchpoint_ingestion_test":
            pytest.fail("Unsafe integration test database")

        connection.execute(
            "DROP TABLE IF EXISTS public.schema_migrations"
        )

        yield connection

    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


def test_registry_creation(db_connection):
    ensure_registry(db_connection)

    result = db_connection.execute(
        """
        SELECT to_regclass(
            'public.schema_migrations'
        ) AS table_name;
        """
    ).fetchone()

    assert result["table_name"] is not None


def test_registry_creation_is_idempotent(db_connection):
    ensure_registry(db_connection)
    ensure_registry(db_connection)

    assert get_applied_migrations(db_connection) == []


def test_record_and_retrieve_migration(db_connection):
    ensure_registry(db_connection)

    record_migration(
        db_connection,
        version=1,
        migration_name="001_create_schemas.sql",
        checksum="a" * 64,
        execution_time_ms=120,
    )

    migrations = get_applied_migrations(db_connection)

    assert len(migrations) == 1

    migration = migrations[0]

    assert migration.version == 1
    assert migration.migration_name == "001_create_schemas.sql"
    assert migration.checksum == "a" * 64
    assert migration.execution_time_ms == 120
    assert migration.applied_at is not None
    assert migration.applied_at.tzinfo is not None


def test_duplicate_version_rejected(db_connection):
    ensure_registry(db_connection)

    record_migration(
        db_connection,
        version=1,
        migration_name="001_create_schemas.sql",
        checksum="a" * 64,
        execution_time_ms=120,
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        record_migration(
            db_connection,
            version=1,
            migration_name="another.sql",
            checksum="b" * 64,
            execution_time_ms=100,
        )


def test_duplicate_migration_name_rejected(db_connection):
    ensure_registry(db_connection)

    record_migration(
        db_connection,
        version=1,
        migration_name="001_create_schemas.sql",
        checksum="a" * 64,
        execution_time_ms=120,
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        record_migration(
            db_connection,
            version=2,
            migration_name="001_create_schemas.sql",
            checksum="b" * 64,
            execution_time_ms=100,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": 0},
        {"version": -1},
        {"migration_name": ""},
        {"migration_name": "   "},
        {"checksum": "invalid"},
        {"checksum": "A" * 64},
        {"checksum": "a" * 63},
        {"execution_time_ms": -1},
    ],
)
def test_invalid_migration_rejected(
    db_connection,
    overrides,
):
    ensure_registry(db_connection)

    values = {
        "version": 1,
        "migration_name": "001_create_schemas.sql",
        "checksum": "a" * 64,
        "execution_time_ms": 120,
    }

    values.update(overrides)

    with pytest.raises(psycopg.errors.CheckViolation):
        record_migration(db_connection, **values)


def test_migrations_returned_in_version_order(db_connection):
    ensure_registry(db_connection)

    for version in (3, 1, 2):
        record_migration(
            db_connection,
            version=version,
            migration_name=f"{version:03d}_migration.sql",
            checksum="a" * 64,
            execution_time_ms=100,
        )

    migrations = get_applied_migrations(db_connection)

    assert [migration.version for migration in migrations] == [
        1, 2, 3
    ]