import os

import psycopg
import pytest

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)


TEST_DATABASE = "matchpoint_e2e_test"


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

        database = conn.execute(
            "SELECT current_database() AS name"
        ).fetchone()["name"]

        assert database == TEST_DATABASE

        count = conn.execute("""
            SELECT COUNT(*) AS total
            FROM bronze.source_listings
        """).fetchone()["total"]

        assert count > 0, "Test fixtures are missing"

    return storage


class RollbackTest(Exception):
    pass


@pytest.mark.parametrize(
    "identifier, constraint",
    [
        ("A" * 513, "chk_source_id_byte_length"),
        ("A" * 10000, "chk_source_id_byte_length"),
        ("\u0627" * 257, "chk_source_id_byte_length"),
        ("\U0001F600" * 129, "chk_source_id_byte_length"),
        (" ABC", "chk_source_id_boundary_whitespace"),
        ("ABC ", "chk_source_id_boundary_whitespace"),
        ("\tABC", "chk_source_id_boundary_whitespace"),
        ("ABC\n", "chk_source_id_boundary_whitespace"),
    ],
)
def test_database_rejects_invalid_identity(
    storage,
    identifier,
    constraint,
):

    with pytest.raises(
        psycopg.errors.CheckViolation
    ) as exc:

        with storage.transaction() as conn:

            conn.execute("""
                UPDATE bronze.source_listings
                SET source_opportunity_id = %s,
                    source_identity_key = %s
                WHERE source_listing_id = (
                    SELECT source_listing_id
                    FROM bronze.source_listings
                    LIMIT 1
                )
            """, (identifier, "id:" + identifier))

            raise RollbackTest(
                "Invalid identity was accepted"
            )

    assert exc.value.diag.constraint_name == constraint


@pytest.mark.parametrize(
    "identifier",
    [
        "A" * 512,
        "\u0627" * 256,
        "\U0001F600" * 128,
    ],
)
def test_database_accepts_valid_boundary(
    storage,
    identifier,
):

    with pytest.raises(RollbackTest):

        with storage.transaction() as conn:

            row = conn.execute("""
                UPDATE bronze.source_listings
                SET source_opportunity_id = %s,
                    source_identity_key = %s
                WHERE source_listing_id = (
                    SELECT source_listing_id
                    FROM bronze.source_listings
                    LIMIT 1
                )
                RETURNING source_opportunity_id
            """, (
                identifier,
                "id:" + identifier,
            )).fetchone()

            assert row["source_opportunity_id"] == identifier

            raise RollbackTest()


def test_original_dataset_preserved(storage):

    with storage.transaction(read_only=True) as conn:

        expected = {
            "collection_runs": 16,
            "source_listings": 40,
            "source_listing_history": 40,
            "ingestion_observations": 80,
            "invalid_records": 0,
            "source_checkpoints": 0,
        }

        for table, total in expected.items():

            actual = conn.execute(
                f"SELECT COUNT(*) AS total FROM bronze.{table}"
            ).fetchone()["total"]

            assert actual == total, table
