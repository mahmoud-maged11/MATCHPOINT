import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)


@pytest.fixture
def storage():
    if os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    settings = PostgresSettings.from_config(
        host="127.0.0.1",
        database="matchpoint_ingestion_test",
    )

    storage = PostgresStorage(settings)

    result = storage.health_check()

    if result["database"] != "matchpoint_ingestion_test":
        pytest.fail("Unsafe integration test database")

    return storage


@pytest.fixture
def test_table(storage):
    table_name = f"transaction_test_{uuid4().hex}"

    table = sql.Identifier("public", table_name)

    with storage.transaction() as conn:
        conn.execute(
            sql.SQL("""
                CREATE TABLE {} (
                    id INTEGER PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """).format(table)
        )

    try:
        yield table

    finally:
        with storage.transaction() as conn:
            conn.execute(
                sql.SQL("DROP TABLE IF EXISTS {}").format(table)
            )


def count_rows(storage, table):
    with storage.transaction(read_only=True) as conn:
        result = conn.execute(
            sql.SQL("SELECT COUNT(*) AS total FROM {}").format(table)
        ).fetchone()

        return result["total"]


def test_health_check(storage):
    result = storage.health_check()

    assert result["database"] == "matchpoint_ingestion_test"
    assert result["read_only"] == "on"


def test_transaction_commit(storage, test_table):
    with storage.transaction() as conn:
        conn.execute(
            sql.SQL("INSERT INTO {} VALUES (%s, %s)").format(
                test_table
            ),
            (1, "committed"),
        )

    assert conn.closed
    assert count_rows(storage, test_table) == 1


def test_transaction_rollback(storage, test_table):
    with pytest.raises(RuntimeError, match="Intentional failure"):
        with storage.transaction() as conn:
            conn.execute(
                sql.SQL("INSERT INTO {} VALUES (%s, %s)").format(
                    test_table
                ),
                (1, "rollback"),
            )

            raise RuntimeError("Intentional failure")

    assert conn.closed
    assert count_rows(storage, test_table) == 0


def test_read_only_rejects_writes(storage, test_table):
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with storage.transaction(read_only=True) as conn:
            conn.execute(
                sql.SQL("INSERT INTO {} VALUES (%s, %s)").format(
                    test_table
                ),
                (1, "forbidden"),
            )

    assert conn.closed
    assert count_rows(storage, test_table) == 0


def test_sql_error_rolls_back_transaction(storage, test_table):
    with pytest.raises(psycopg.errors.UniqueViolation):
        with storage.transaction() as conn:
            statement = sql.SQL(
                "INSERT INTO {} VALUES (%s, %s)"
            ).format(test_table)

            conn.execute(statement, (1, "first"))
            conn.execute(statement, (2, "second"))
            conn.execute(statement, (1, "duplicate"))

    assert conn.closed
    assert count_rows(storage, test_table) == 0


def test_successful_connection_closure(storage):
    with storage.transaction(read_only=True) as conn:
        assert not conn.closed

    assert conn.closed


def test_exception_connection_closure(storage):
    with pytest.raises(RuntimeError, match="Test exception"):
        with storage.transaction() as conn:
            raise RuntimeError("Test exception")

    assert conn.closed


def test_password_hidden(storage):
    assert storage.settings.password not in repr(storage.settings)