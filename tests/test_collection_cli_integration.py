import json
import os

from pathlib import Path
from uuid import UUID

import pytest

from scrapers import main as cli

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.migration_runner import (
    MigrationRunner,
)


TEST_DATABASE = "matchpoint_cli_test"

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "wuzzuf_synthetic.html"
)


@pytest.fixture
def storage(monkeypatch):

    if os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests disabled")

    monkeypatch.setattr(
        "scrapers.config.REJECTION_FINGERPRINT_KEY",
        "matchpoint-offline-test-key-not-for-production",
    )

    storage = PostgresStorage(
        PostgresSettings.from_config(
            host="127.0.0.1",
            database=TEST_DATABASE,
        )
    )

    MigrationRunner(storage).run()

    def reset():
        with storage.transaction() as conn:

            row = conn.execute(
                "SELECT current_database() AS name"
            ).fetchone()

            if row["name"] != TEST_DATABASE:
                raise RuntimeError("Unsafe test database")

            conn.execute("""
                TRUNCATE TABLE
                    bronze.source_checkpoints,
                    bronze.invalid_records,
                    bronze.ingestion_observations,
                    bronze.source_listing_history,
                    bronze.source_listings,
                    bronze.collection_runs
            """)

    reset()

    try:
        yield storage
    finally:
        reset()


def execute_cli(
    html_path,
    *,
    output=None,
):
    arguments = [
        "--source", "wuzzuf",
        "--mode", "html",
        "--html-path", str(html_path),
        "--storage", "both" if output else "postgres",
        "--postgres-host", "127.0.0.1",
        "--postgres-db", TEST_DATABASE,
    ]

    if output is not None:
        arguments.extend([
            "--output", str(output),
        ])

    assert cli.main(arguments) == 0


def get_counts(storage):
    with storage.transaction() as conn:
        return conn.execute("""
            SELECT
                (
                    SELECT COUNT(*)
                    FROM bronze.source_listings
                ) AS listings,
                (
                    SELECT COUNT(*)
                    FROM bronze.source_listing_history
                ) AS history,
                (
                    SELECT COUNT(*)
                    FROM bronze.ingestion_observations
                ) AS observations,
                (
                    SELECT COUNT(*)
                    FROM bronze.invalid_records
                ) AS invalid_records,
                (
                    SELECT COUNT(*)
                    FROM bronze.collection_runs
                ) AS runs
        """).fetchone()


def get_latest_run(storage):
    with storage.transaction() as conn:
        return conn.execute("""
            SELECT *
            FROM bronze.collection_runs
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
        """).fetchone()


def assert_counters(
    run,
    *,
    inserted,
    updated,
    unchanged,
):
    assert run["status"] == "completed"
    assert run["records_received"] == 5
    assert run["records_inserted"] == inserted
    assert run["records_updated"] == updated
    assert run["records_unchanged"] == unchanged
    assert run["records_invalid"] == 2
    assert run["records_stale"] == 0
    assert run["records_conflicted"] == 0
    assert run["finished_at"] is not None


def test_cli_initial_ingestion(
    storage,
    tmp_path,
):
    output = tmp_path / "opportunities.json"

    execute_cli(FIXTURE, output=output)

    run = get_latest_run(storage)

    assert_counters(
        run,
        inserted=3,
        updated=0,
        unchanged=0,
    )

    assert isinstance(run["run_id"], UUID)

    assert get_counts(storage) == {
        "listings": 3,
        "history": 3,
        "observations": 3,
        "invalid_records": 2,
        "runs": 1,
    }

    records = json.loads(
        output.read_text(encoding="utf-8")
    )

    assert len(records) == 3

    assert {
        record["source_opportunity_id"]
        for record in records
    } == {"test001", "test002", "test003"}


def test_cli_repeated_collection(storage):

    execute_cli(FIXTURE)

    first_run = get_latest_run(storage)

    execute_cli(FIXTURE)

    second_run = get_latest_run(storage)

    assert first_run["run_id"] != second_run["run_id"]

    assert_counters(
        second_run,
        inserted=0,
        updated=0,
        unchanged=3,
    )

    assert get_counts(storage) == {
        "listings": 3,
        "history": 3,
        "observations": 6,
        "invalid_records": 4,
        "runs": 2,
    }

    with storage.transaction() as conn:
        rows = conn.execute("""
            SELECT
                content_version,
                last_seen_at > first_seen_at AS seen_again
            FROM bronze.source_listings
        """).fetchall()

    assert len(rows) == 3

    assert all(
        row["content_version"] == 1
        and row["seen_again"]
        for row in rows
    )


def test_cli_content_change(
    storage,
    tmp_path,
):
    execute_cli(FIXTURE)

    html = FIXTURE.read_text(encoding="utf-8-sig")

    assert html.count("Data Engineer") == 1

    modified = tmp_path / "modified.html"

    modified.write_text(
        html.replace(
            "Data Engineer",
            "Senior Data Engineer",
            1,
        ),
        encoding="utf-8",
    )

    execute_cli(modified)

    assert_counters(
        get_latest_run(storage),
        inserted=0,
        updated=1,
        unchanged=2,
    )

    assert get_counts(storage) == {
        "listings": 3,
        "history": 4,
        "observations": 6,
        "invalid_records": 4,
        "runs": 2,
    }

    with storage.transaction() as conn:

        listing = conn.execute("""
            SELECT title, content_version
            FROM bronze.source_listings
            WHERE source_name = 'wuzzuf'
              AND source_opportunity_id = 'test001'
        """).fetchone()

        history = conn.execute("""
            SELECT
                h.content_version,
                h.standardized_payload->>'title' AS title
            FROM bronze.source_listing_history h
            JOIN bronze.source_listings s
                ON s.source_listing_id = h.source_listing_id
            WHERE s.source_name = 'wuzzuf'
              AND s.source_opportunity_id = 'test001'
            ORDER BY h.content_version
        """).fetchall()

    assert listing["title"] == "Senior Data Engineer"
    assert listing["content_version"] == 2

    assert history == [
        {
            "content_version": 1,
            "title": "Data Engineer",
        },
        {
            "content_version": 2,
            "title": "Senior Data Engineer",
        },
    ]