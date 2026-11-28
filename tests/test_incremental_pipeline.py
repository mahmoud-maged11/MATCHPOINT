import os

from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from scrapers.checkpoint_intent import CheckpointIntent

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)
from scrapers.storage.checkpoints import (
    CheckpointRepository,
)
from scrapers.storage.collection_snapshot import (
    CollectionSnapshotStore,
)
from scrapers.storage.orchestrator import (
    IngestionOrchestrator,
    IngestionExecutionError,
)
from scrapers.storage.recovery_lock import (
    RecoveryLockManager,
)
from scrapers.storage.rejection_policy import (
    RejectionPolicy,
)

from test_egyincs_incremental import (
    WINDOW,
    scraper_for,
    record,
    response,
)


pytestmark = pytest.mark.skipif(
    os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1",
    reason="Requires isolated PostgreSQL database",
)


@pytest.fixture
def pipeline(tmp_path):

    storage = PostgresStorage(
        PostgresSettings.from_config(
            host="127.0.0.1",
            database="matchpoint_ingestion_test",
        )
    )

    assert storage.health_check()["database"] == (
        "matchpoint_ingestion_test"
    )

    store = CollectionSnapshotStore(
        tmp_path / "snapshots",
        integrity_key=b"x" * 32,
    )

    def new_orchestrator():

        return IngestionOrchestrator(
            storage,
            rejection_policy=RejectionPolicy(b"x" * 32),
            snapshot_store=store,
            recovery_lock=RecoveryLockManager(storage),
        )

    run_id = uuid4()

    intent = CheckpointIntent(
        run_id=run_id,
        source_name="egyincs",
        collection_scope="jobs",
        previous_run_id=None,
        previous_watermark=(
            WINDOW.lower + timedelta(minutes=5)
        ),
        window=WINDOW,
    )

    repository = CheckpointRepository(storage)

    def checkpoint():

        return repository.get_checkpoint(
            source_name="egyincs",
            collection_scope="jobs",
        )

    assert checkpoint() is None

    try:

        yield {
            "orchestrator": new_orchestrator(),
            "new_orchestrator": new_orchestrator,
            "intent": intent,
            "run_id": run_id,
            "checkpoint": checkpoint,
            "store": store,
        }

    finally:

        with storage.transaction() as conn:

            conn.execute("""
                DELETE FROM bronze.source_checkpoints
                WHERE last_successful_run_id = %s
            """, (run_id,))

            for table in (
                "ingestion_observations",
                "source_listing_history",
                "invalid_records",
            ):

                conn.execute(
                    f"DELETE FROM bronze.{table} "
                    "WHERE collection_run_id = %s",
                    (run_id,),
                )

            conn.execute("""
                DELETE FROM bronze.source_listings
                WHERE last_collection_run_id = %s
            """, (run_id,))

            conn.execute("""
                DELETE FROM bronze.collection_runs
                WHERE run_id = %s
            """, (run_id,))


def make_scraper(*, empty=False, limited=False):

    scraper = scraper_for(
        max_pages=1 if limited else None
    )

    pages = (
        [response([], 0, 0)]
        if empty
        else [
            response([record(1), record(2)], 3, 2),
            response([record(3)], 3, 2),
        ]
    )

    scraper.fetch = Mock(side_effect=pages)

    return scraper


def execute(pipeline, scraper):

    return pipeline["orchestrator"].execute(
        scraper=scraper,
        collection_mode="api",
        collection_scope="jobs",
        run_id=pipeline["run_id"],
        checkpoint_intent=pipeline["intent"],
    )


def assert_advanced(pipeline, row, expected_count):

    assert row["status"] == "completed"

    assert row["records_received"] == expected_count
    assert row["records_invalid"] == 0
    assert row["records_stale"] == 0
    assert row["records_conflicted"] == 0

    metadata = row["metadata"]

    assert metadata["checkpoint_intent"] == (
        pipeline["intent"].to_metadata()
    )

    assert metadata["checkpoint_coverage"][
        "accepted_count"
    ] == expected_count

    receipt = metadata["checkpoint_finalization"]

    assert receipt["outcome"] == "advanced"

    checkpoint = pipeline["checkpoint"]()

    assert checkpoint["last_successful_run_id"] == (
        pipeline["run_id"]
    )

    assert checkpoint["checkpoint_value"] == {
        "timestamp": (
            pipeline["intent"].target_watermark.isoformat()
        )
    }

    assert receipt["checkpoint_value"] == (
        checkpoint["checkpoint_value"]
    )


@pytest.mark.parametrize(
    "empty,expected_count",
    [(False, 3), (True, 0)],
)
def test_incremental_success(
    pipeline,
    empty,
    expected_count,
):

    result = execute(
        pipeline,
        make_scraper(empty=empty),
    )

    assert_advanced(
        pipeline,
        result.finalized_run,
        expected_count,
    )


def test_limited_collection(pipeline):

    result = execute(
        pipeline,
        make_scraper(limited=True),
    )

    row = result.finalized_run

    assert row["status"] == "completed"
    assert row["records_received"] == 2

    assert "checkpoint_coverage" not in row["metadata"]
    assert "checkpoint_finalization" not in row["metadata"]

    assert pipeline["checkpoint"]() is None


def test_crash_before_coverage_sealing(
    pipeline,
    monkeypatch,
):

    orchestrator = pipeline["orchestrator"]

    def crash(**kwargs):
        raise RuntimeError("Crash before coverage seal")

    monkeypatch.setattr(
        orchestrator.runs,
        "seal_checkpoint_coverage",
        crash,
    )

    with pytest.raises(IngestionExecutionError):

        execute(pipeline, make_scraper())

    row = orchestrator.runs.get_run(
        pipeline["run_id"]
    )

    assert row["status"] == "running"
    assert "checkpoint_intent" in row["metadata"]
    assert "checkpoint_coverage" not in row["metadata"]

    assert pipeline["store"].load(
        pipeline["run_id"]
    ).accepted_count == 3

    assert pipeline["checkpoint"]() is None

    recovered = pipeline["new_orchestrator"]().recover(
        run_id=pipeline["run_id"],
    )

    assert recovered.finalized_run["status"] == "completed"
    assert recovered.finalized_run["records_received"] == 3

    assert pipeline["checkpoint"]() is None


def test_crash_after_coverage_sealing(
    pipeline,
    monkeypatch,
):

    orchestrator = pipeline["orchestrator"]

    def crash(result):
        raise RuntimeError("Crash after coverage seal")

    monkeypatch.setattr(
        orchestrator,
        "persist_collection",
        crash,
    )

    with pytest.raises(RuntimeError, match="after coverage"):

        execute(pipeline, make_scraper())

    row = orchestrator.runs.get_run(
        pipeline["run_id"]
    )

    assert row["status"] == "running"
    assert "checkpoint_coverage" in row["metadata"]

    assert pipeline["checkpoint"]() is None

    recovered = pipeline["new_orchestrator"]().recover(
        run_id=pipeline["run_id"],
    )

    assert_advanced(
        pipeline,
        recovered.finalized_run,
        3,
    )


def test_repeated_recovery(pipeline):

    result = execute(
        pipeline,
        make_scraper(),
    )

    assert_advanced(
        pipeline,
        result.finalized_run,
        3,
    )

    before = pipeline["checkpoint"]()

    recovered = pipeline["new_orchestrator"]().recover(
        run_id=pipeline["run_id"],
    )

    assert recovered.already_finalized

    assert recovered.finalized_run == (
        result.finalized_run
    )

    assert pipeline["checkpoint"]() == before
