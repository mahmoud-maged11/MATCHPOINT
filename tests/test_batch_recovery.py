from unittest.mock import Mock

import psycopg
import pytest

from scrapers.storage.orchestrator import (
    IngestionExecutionError,
)

from test_incremental_pipeline import (
    pipeline,
    make_scraper,
    execute,
)


def persisted_counts(pipeline):

    orchestrator = pipeline["orchestrator"]
    run_id = pipeline["run_id"]

    tables = {
        "listings": (
            "source_listings",
            "last_collection_run_id",
        ),
        "history": (
            "source_listing_history",
            "collection_run_id",
        ),
        "observations": (
            "ingestion_observations",
            "collection_run_id",
        ),
    }

    with orchestrator.storage.transaction(
        read_only=True
    ) as conn:

        return {
            key: conn.execute(
                f"SELECT COUNT(*) AS n "
                f"FROM bronze.{table} "
                f"WHERE {column} = %s",
                (run_id,),
            ).fetchone()["n"]
            for key, (table, column) in tables.items()
        }


def assert_counts(pipeline, expected):

    assert persisted_counts(pipeline) == {
        "listings": expected,
        "history": expected,
        "observations": expected,
    }


def assert_completed(pipeline, result):

    row = result.finalized_run

    assert row["status"] == "completed"

    assert row["records_received"] == 3
    assert row["records_inserted"] == 3

    for field in (
        "updated",
        "unchanged",
        "invalid",
        "stale",
        "conflicted",
    ):

        assert row[f"records_{field}"] == 0

    assert (
        row["metadata"]
        ["checkpoint_finalization"]
        ["outcome"]
        == "advanced"
    )

    assert pipeline["checkpoint"]() is not None

    assert_counts(pipeline, 3)


@pytest.mark.parametrize(
    "recovery_batch_size",
    [1, 2, 100],
)
def test_recover_after_second_batch_failure(
    pipeline,
    monkeypatch,
    recovery_batch_size,
):

    orchestrator = pipeline["orchestrator"]

    orchestrator.batch_size = 2

    repository = orchestrator.opportunities

    original = repository.ingest_many

    calls = 0

    def fail_second_batch(records, run_id):

        nonlocal calls

        calls += 1

        if calls == 2:

            raise RuntimeError(
                "Injected second batch failure"
            )

        return original(records, run_id)

    monkeypatch.setattr(
        repository,
        "ingest_many",
        fail_second_batch,
    )

    with pytest.raises(
        IngestionExecutionError
    ) as error:

        execute(
            pipeline,
            make_scraper(),
        )

    assert error.value.stage == "accepted_persistence"

    assert calls == 2

    assert_counts(pipeline, 2)

    assert pipeline["checkpoint"]() is None

    recovery = pipeline["new_orchestrator"]()

    recovery.batch_size = recovery_batch_size

    result = recovery.recover(
        run_id=pipeline["run_id"],
    )

    assert_completed(pipeline, result)

    repeated = recovery.recover(
        run_id=pipeline["run_id"],
    )

    assert repeated.already_finalized

    assert repeated.finalized_run == result.finalized_run

    assert_counts(pipeline, 3)


@pytest.mark.parametrize(
    "error_type",
    [
        psycopg.errors.DeadlockDetected,
        psycopg.errors.SerializationFailure,
    ],
)
def test_retryable_batch_transaction_failure(
    pipeline,
    monkeypatch,
    error_type,
):

    orchestrator = pipeline["orchestrator"]

    orchestrator.batch_size = 100

    repository = orchestrator.opportunities

    original = repository._insert_observation

    calls = 0

    def fail_once(*args, **kwargs):

        nonlocal calls

        calls += 1

        if calls == 2:

            raise error_type(
                "Injected retryable transaction failure"
            )

        return original(*args, **kwargs)

    monkeypatch.setattr(
        repository,
        "_insert_observation",
        fail_once,
    )

    result = execute(
        pipeline,
        make_scraper(),
    )

    # Two attempted records in the failed transaction,
    # followed by three records in the retried batch.

    assert calls == 5

    assert_completed(pipeline, result)


def test_batch_ambiguous_commit_replay(
    pipeline,
    monkeypatch,
):

    orchestrator = pipeline["orchestrator"]

    orchestrator.batch_size = 100

    repository = orchestrator.opportunities

    original = repository.ingest_many

    attempts = 0

    def commit_then_fail(records, run_id):

        nonlocal attempts

        attempts += 1

        result = original(
            records,
            run_id,
        )

        if attempts == 1:

            raise psycopg.errors.ConnectionFailure(
                "Injected lost commit acknowledgement"
            )

        return result

    monkeypatch.setattr(
        repository,
        "ingest_many",
        commit_then_fail,
    )

    result = execute(
        pipeline,
        make_scraper(),
    )

    assert attempts == 2

    assert result.accepted.processed == 3

    assert all(
        item.outcome == "duplicate"
        and item.original_outcome == "inserted"
        for item in result.accepted.outcomes
    )

    assert_completed(pipeline, result)
