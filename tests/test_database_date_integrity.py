import os
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg import sql

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)


TEST_DATABASE = "matchpoint_e2e_test"

TIMESTAMP = datetime(
    2026, 11, 27, 12, 0,
    tzinfo=timezone.utc,
)


class RollbackTest(Exception):
    pass


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

    with storage.transaction(read_only=True) as conn:

        actual = conn.execute(
            "SELECT current_database() AS name"
        ).fetchone()["name"]

        assert actual == TEST_DATABASE

        count = conn.execute("""
            SELECT COUNT(*) AS total
            FROM bronze.source_listings
        """).fetchone()["total"]

        assert count > 0

    return storage


def update_date(conn, field, value, precision, raw):

    query = sql.SQL("""
        UPDATE bronze.source_listings
        SET {} = %s,
            {} = %s,
            {} = %s
        WHERE source_listing_id = (
            SELECT source_listing_id
            FROM bronze.source_listings
            ORDER BY source_listing_id
            LIMIT 1
        )
        RETURNING source_listing_id
    """).format(
        sql.Identifier(field),
        sql.Identifier(f"{field}_precision"),
        sql.Identifier(f"{field}_raw"),
    )

    row = conn.execute(
        query,
        (value, precision, raw),
    ).fetchone()

    assert row is not None


@pytest.mark.parametrize(
    "field",
    ["published_at", "deadline"],
)
@pytest.mark.parametrize(
    "value,precision,raw",
    [
        (TIMESTAMP, None, None),
        (None, "exact", None),
        (TIMESTAMP, "date_only", "2026-11-27"),
        (None, "date_only", None),
        (None, "date_only", ""),
        (None, "date_only", " "),
        (None, "relative", None),
        (None, "relative", ""),
        (TIMESTAMP, "relative", "\t\n"),
    ],
)
def test_database_rejects_invalid_date(
    storage,
    field,
    value,
    precision,
    raw,
):

    with pytest.raises(
        psycopg.errors.CheckViolation
    ) as exc:

        with storage.transaction() as conn:

            update_date(
                conn, field, value, precision, raw
            )

            raise RollbackTest(
                "Invalid date combination accepted"
            )

    assert exc.value.diag.constraint_name == (
        f"chk_{field}_precision_consistency"
    )


@pytest.mark.parametrize(
    "field",
    ["published_at", "deadline"],
)
@pytest.mark.parametrize(
    "value,precision,raw",
    [
        (None, None, None),
        (None, "unknown", "Unavailable"),
        (None, "date_only", "2026-11-27"),
        (TIMESTAMP, "exact", None),
        (TIMESTAMP, "relative", "2 hours ago"),
        (None, "relative", "Recently"),
    ],
)
def test_database_accepts_valid_date(
    storage,
    field,
    value,
    precision,
    raw,
):

    with pytest.raises(RollbackTest):

        with storage.transaction() as conn:

            update_date(
                conn, field, value, precision, raw
            )

            raise RollbackTest()


def test_dataset_counts_preserved(storage):

    expected = {
        "collection_runs": 16,
        "source_listings": 40,
        "source_listing_history": 40,
        "ingestion_observations": 80,
        "invalid_records": 0,
        "source_checkpoints": 0,
    }

    with storage.transaction(read_only=True) as conn:

        for table, count in expected.items():

            query = sql.SQL("""
                SELECT COUNT(*) AS total
                FROM bronze.{}
            """).format(sql.Identifier(table))

            actual = conn.execute(
                query
            ).fetchone()["total"]

            assert actual == count, table
