import os
from uuid import uuid4

import pytest
import psycopg

from scrapers.models import Opportunity

from scrapers.storage.opportunities import (
    OpportunityRepository,
)

from scrapers.storage.invalid_records import (
    InvalidRecordRepository,
)

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.collection_runs import (
    CollectionRunManager,
    CollectionRunError,
    RunCounters,
)


@pytest.fixture
def manager():

    if os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    settings = PostgresSettings.from_config(
        host="127.0.0.1",
        database="matchpoint_ingestion_test",
    )

    storage = PostgresStorage(settings)

    if storage.health_check()["database"] != "matchpoint_ingestion_test":
        pytest.fail("Unsafe integration test database")

    return CollectionRunManager(storage)


@pytest.fixture
def run_id(manager):

    identifier = uuid4()

    manager.start_run(
        run_id=identifier,
        source_name="wuzzuf",
        collection_mode="api",
        collection_scope="integration_test",
        metadata={"test": True},
    )

    try:
        yield identifier

    finally:
        with manager.storage.transaction() as conn:

            for table in (
                "invalid_records",
                "ingestion_observations",
                "source_listing_history",
            ):

                from psycopg import sql

                conn.execute(
                    sql.SQL(
                        "DELETE FROM bronze.{} "
                        "WHERE collection_run_id = %s"
                    ).format(sql.Identifier(table)),
                    (identifier,),
                )

            conn.execute(
                """
                DELETE FROM bronze.source_listings
                WHERE last_collection_run_id = %s
                """,
                (identifier,),
            )

            conn.execute(
                """
                DELETE FROM bronze.collection_runs
                WHERE run_id = %s
                """,
                (identifier,),
            )


def test_start_run(manager, run_id):

    run = manager.get_run(run_id)

    assert run["run_id"] == run_id
    assert run["source_name"] == "wuzzuf"
    assert run["collection_mode"] == "api"
    assert run["collection_scope"] == "integration_test"
    assert run["status"] == "running"
    assert run["finished_at"] is None
    assert run["contract_version"] == "3.0.0"
    assert run["hash_version"] == 1
    assert run["metadata"] == {"test": True}
    assert run["records_received"] == 0


def test_missing_run(manager):

    assert manager.get_run(uuid4()) is None


def persist_listings(manager, run_id, count):

    repository = OpportunityRepository(manager.storage)

    for _ in range(count):

        identifier = uuid4().hex

        opportunity = Opportunity(
            source_name="wuzzuf",
            source_opportunity_id=identifier,
            source_url=(
                f"https://wuzzuf.net/jobs/p/{identifier}"
            ),
            title="Data Engineer",
            opportunity_type="job",
            raw_payload={"id": identifier},
        )

        result = repository.ingest(
            opportunity,
            run_id,
        )

        assert result.outcome == "inserted"


def test_complete_run(manager, run_id):

    persist_listings(manager, run_id, 3)

    rejection = InvalidRecordRepository(
        manager.storage
    ).record(
        run_id=run_id,
        source_name="wuzzuf",
        failure_stage="validation",
        error_code="MissingTitle",
        error_message="Required title is missing",
        record_payload={"title": None},
    )

    assert rejection.inserted is True

    counters = RunCounters(
        received=4,
        inserted=3,
        invalid=1,
    )

    result = manager.finish_run(
        run_id=run_id,
        status="completed",
        counters=counters,
    )

    assert result["status"] == "completed"
    assert result["finished_at"] >= result["started_at"]
    assert result["error_message"] is None

    for name in (
        "received",
        "inserted",
        "updated",
        "unchanged",
        "invalid",
        "stale",
        "conflicted",
    ):
        assert result[f"records_{name}"] == getattr(
            counters,
            name,
        )

    assert manager.get_run(run_id) == result


@pytest.mark.parametrize(
    "status",
    ["partial", "failed", "aborted"],
)
def test_unsuccessful_run(manager, run_id, status):

    persist_listings(manager, run_id, 3)

    result = manager.finish_run(
        run_id=run_id,
        status=status,
        counters=RunCounters(
            received=10,
            inserted=3,
        ),
        error_message="Integration test failure",
    )

    assert result["status"] == status
    assert result["records_received"] == 10
    assert result["records_inserted"] == 3
    assert result["finished_at"] >= result["started_at"]
    assert result["error_message"] == "Integration test failure"


def test_duplicate_finalization(manager, run_id):

    manager.finish_run(
        run_id=run_id,
        status="completed",
        counters=RunCounters(),
    )

    original = manager.get_run(run_id)

    with pytest.raises(CollectionRunError):
        manager.finish_run(
            run_id=run_id,
            status="failed",
            counters=RunCounters(),
            error_message="Unexpected failure",
        )

    assert manager.get_run(run_id) == original


def test_finalize_missing_run(manager):

    with pytest.raises(CollectionRunError):
        manager.finish_run(
            run_id=uuid4(),
            status="completed",
            counters=RunCounters(),
        )


def test_duplicate_run_id(manager, run_id):

    original = manager.get_run(run_id)

    with pytest.raises(psycopg.errors.UniqueViolation):
        manager.start_run(
            run_id=run_id,
            source_name="bayt",
            collection_mode="html",
        )

    assert manager.get_run(run_id) == original


def test_completed_run_rejects_unprocessed(manager, run_id):

    persist_listings(manager, run_id, 5)

    before = manager.get_run(run_id)

    with pytest.raises(
        ValueError,
        match="Completed runs cannot contain unprocessed records",
    ):
        manager.finish_run(
            run_id=run_id,
            status="completed",
            counters=RunCounters(
                received=10,
                inserted=5,
            ),
        )

    assert manager.get_run(run_id) == before


def test_completed_run_rejects_error(manager, run_id):

    with pytest.raises(ValueError):
        manager.finish_run(
            run_id=run_id,
            status="completed",
            counters=RunCounters(),
            error_message="Unexpected error",
        )

    assert manager.get_run(run_id)["status"] == "running"


@pytest.mark.parametrize(
    "status",
    ["partial", "failed", "aborted"],
)
def test_unsuccessful_run_requires_error(
    manager,
    run_id,
    status,
):

    with pytest.raises(ValueError):
        manager.finish_run(
            run_id=run_id,
            status=status,
            counters=RunCounters(),
        )

    assert manager.get_run(run_id)["status"] == "running"


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_name": "unsupported"},
        {"collection_mode": "invalid"},
        {"collection_scope": "   "},
        {"metadata": []},
        {"run_id": "invalid-uuid"},
    ],
)
def test_invalid_run_configuration(manager, overrides):

    arguments = {
        "source_name": "wuzzuf",
        "collection_mode": "api",
        "collection_scope": "integration_test",
    }

    arguments.update(overrides)

    with pytest.raises(ValueError):
        manager.start_run(**arguments)


def test_invalid_final_status(manager, run_id):

    with pytest.raises(ValueError):
        manager.finish_run(
            run_id=run_id,
            status="running",
            counters=RunCounters(),
        )

    assert manager.get_run(run_id)["status"] == "running"


@pytest.mark.parametrize(
    "arguments",
    [
        {"received": -1},
        {"received": 1, "inserted": 2},
        {"received": 5, "updated": -1},
        {"received": 1.5},
        {"received": True},
        {"received": 2, "inserted": 1, "invalid": 2},
    ],
)
def test_invalid_counters(arguments):

    with pytest.raises(ValueError):
        RunCounters(**arguments)


def test_counter_calculations():

    counters = RunCounters(
        received=20,
        inserted=5,
        updated=3,
        unchanged=2,
        invalid=1,
        stale=1,
        conflicted=1,
    )

    assert counters.processed == 13
    assert counters.unprocessed == 7