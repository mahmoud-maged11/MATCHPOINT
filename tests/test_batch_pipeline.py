from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from scrapers.storage.orchestrator import (
    IngestionOrchestrator,
    IngestionExecutionError,
)

from test_incremental_pipeline import (
    pipeline,
    make_scraper,
    execute,
    assert_advanced,
)


@pytest.mark.parametrize(
    "value",
    [True, False, None, "100", 1.5],
)
def test_batch_size_type_validation(value):

    with pytest.raises(TypeError, match="integer"):

        IngestionOrchestrator(
            Mock(),
            batch_size=value,
        )


@pytest.mark.parametrize(
    "value",
    [-1, 0, 1001],
)
def test_batch_size_range_validation(value):

    with pytest.raises(ValueError, match="between"):

        IngestionOrchestrator(
            Mock(),
            batch_size=value,
        )


@pytest.mark.parametrize(
    "value",
    [1, 2, 100, 1000],
)
def test_valid_batch_sizes(value):

    orchestrator = IngestionOrchestrator(
        Mock(),
        batch_size=value,
    )

    assert orchestrator.batch_size == value


def test_default_preserves_single_record_behavior():

    orchestrator = IngestionOrchestrator(Mock())

    assert orchestrator.batch_size == 1


def test_batch_incremental_completion(
    pipeline,
    monkeypatch,
):

    orchestrator = pipeline["orchestrator"]

    orchestrator.batch_size = 100

    repository = orchestrator.opportunities

    ingest_many = Mock(
        wraps=repository.ingest_many
    )

    monkeypatch.setattr(
        repository,
        "ingest_many",
        ingest_many,
    )

    result = execute(
        pipeline,
        make_scraper(),
    )

    assert result.finalized_run["status"] == "completed"

    assert result.finalized_run["records_inserted"] == 3

    assert result.accepted.processed == 3

    ingest_many.assert_called_once()

    records, run_id = ingest_many.call_args.args

    assert len(records) == 3

    assert run_id == pipeline["run_id"]

    assert (
        result.finalized_run["metadata"]
        ["checkpoint_finalization"]["outcome"]
        == "advanced"
    )

    assert pipeline["checkpoint"]() is not None


def test_multiple_batches(
    pipeline,
    monkeypatch,
):

    orchestrator = pipeline["orchestrator"]

    orchestrator.batch_size = 2

    repository = orchestrator.opportunities

    ingest_many = Mock(
        wraps=repository.ingest_many
    )

    monkeypatch.setattr(
        repository,
        "ingest_many",
        ingest_many,
    )

    result = execute(
        pipeline,
        make_scraper(),
    )

    assert result.accepted.processed == 3

    assert [
        len(call.args[0])
        for call in ingest_many.call_args_list
    ] == [2, 1]

    assert result.finalized_run["records_inserted"] == 3


def test_empty_incremental_does_not_open_batch(
    pipeline,
    monkeypatch,
):

    orchestrator = pipeline["orchestrator"]

    orchestrator.batch_size = 100

    repository = orchestrator.opportunities

    ingest_many = Mock(
        wraps=repository.ingest_many
    )

    monkeypatch.setattr(
        repository,
        "ingest_many",
        ingest_many,
    )

    result = execute(
        pipeline,
        make_scraper(empty=True),
    )

    assert result.accepted.processed == 0

    ingest_many.assert_not_called()

    assert (
        result.finalized_run["metadata"]
        ["checkpoint_finalization"]["outcome"]
        == "advanced"
    )


def test_real_batch_rollback_and_recovery(
    pipeline,
    monkeypatch,
):

    orchestrator = pipeline["orchestrator"]

    orchestrator.batch_size = 100

    repository = orchestrator.opportunities

    original_insert = repository._insert_observation

    calls = 0

    def fail_second(*args, **kwargs):

        nonlocal calls

        calls += 1

        if calls == 2:

            raise RuntimeError(
                "Injected batch failure"
            )

        return original_insert(
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        repository,
        "_insert_observation",
        fail_second,
    )

    with pytest.raises(IngestionExecutionError) as error:

        execute(
            pipeline,
            make_scraper(),
        )

    assert error.value.stage == "accepted_persistence"

    assert calls == 2

    assert pipeline["checkpoint"]() is None

    run_id = pipeline["run_id"]

    with orchestrator.storage.transaction(
        read_only=True
    ) as conn:

        for table, column in (
            (
                "source_listings",
                "last_collection_run_id",
            ),
            (
                "source_listing_history",
                "collection_run_id",
            ),
            (
                "ingestion_observations",
                "collection_run_id",
            ),
        ):

            row = conn.execute(
                f"SELECT COUNT(*) AS n "
                f"FROM bronze.{table} "
                f"WHERE {column} = %s",
                (run_id,),
            ).fetchone()

            assert row["n"] == 0, table

    recovery = pipeline["new_orchestrator"]()

    recovery.batch_size = 100

    result = recovery.recover(
        run_id=run_id,
    )

    assert result.finalized_run["status"] == "completed"

    assert result.finalized_run["records_inserted"] == 3

    assert (
        result.finalized_run["metadata"]
        ["checkpoint_finalization"]["outcome"]
        == "advanced"
    )

    assert pipeline["checkpoint"]() is not None

    repeated = recovery.recover(
        run_id=run_id,
    )

    assert repeated.already_finalized

    assert (
        repeated.finalized_run
        == result.finalized_run
    )
