from contextlib import nullcontext
from datetime import datetime, timezone
from unittest.mock import Mock

import psycopg
import pytest

from scrapers.storage.collection_runs import (
    CONTRACT_VERSION,
    RunCounters,
)

from scrapers.utils.hashing import HASH_VERSION

from scrapers.storage.retry_policy import RetryPolicy

from scrapers.storage.run_recovery import (
    COUNTER_FIELDS,
    RunRecoveryError,
)

from scrapers.storage.orchestrator import (
    IngestionExecutionError,
)

from test_orchestrator_execution import (
    orchestrator,
    run_id,
    opportunity,
    make_result,
    make_rejection,
    make_scraper,
)


@pytest.fixture
def recovery_orchestrator(orchestrator):

    orchestrator.retry_policy = RetryPolicy(
        max_attempts=3,
        initial_delay=0,
    )

    return orchestrator


def make_running_row(run_id):

    return {
        "run_id": run_id,
        "source_name": "wuzzuf",
        "collection_mode": "api",
        "collection_scope": "default",
        "metadata": {},
        "contract_version": CONTRACT_VERSION,
        "hash_version": HASH_VERSION,
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "finished_at": None,
        "error_message": None,
        **{
            f"records_{field}": 0
            for field in COUNTER_FIELDS
        },
    }


def configure_finalization(
    instance,
    run_id,
    monkeypatch,
    *,
    received=0,
    inserted=0,
    invalid=0,
):

    row = make_running_row(run_id)

    row.update({
        "status": "completed",
        "finished_at": datetime.now(timezone.utc),
        "records_received": received,
        "records_inserted": inserted,
        "records_invalid": invalid,
    })

    connection = Mock()

    connection.execute.return_value.fetchone.return_value = (
        row
    )

    instance.runs.storage.transaction.return_value = (
        nullcontext(connection)
    )

    calculate = Mock(
        return_value=RunCounters(
            received=received,
            inserted=inserted,
            updated=0,
            unchanged=0,
            invalid=invalid,
            stale=0,
            conflicted=0,
        )
    )

    monkeypatch.setattr(
        "scrapers.storage.run_recovery."
        "RunCounterRepository.calculate",
        calculate,
    )

    return row, connection, calculate


def test_creation_acknowledgement_recovery(
    recovery_orchestrator, run_id
):

    instance = recovery_orchestrator

    instance.runs.start_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    instance.runs.get_run.return_value = (
        make_running_row(run_id)
    )

    scraper = make_scraper(make_result(run_id))

    executed = instance.execute(
        scraper=scraper,
        collection_mode="api",
        run_id=run_id,
    )

    assert executed.run_id == run_id

    instance.runs.start_run.assert_called_once()

    scraper.run_with_result.assert_called_once_with(
        run_id=run_id
    )

    instance.runs.finish_run.assert_called_once()


def test_creation_rollback_recovery(
    recovery_orchestrator, run_id
):

    instance = recovery_orchestrator

    instance.runs.start_run.side_effect = [
        psycopg.errors.ConnectionFailure(),
        run_id,
    ]

    instance.runs.get_run.side_effect = [
        None,
        *[
            make_running_row(run_id)
            for _ in range(10)
        ],
    ]

    scraper = make_scraper(make_result(run_id))

    executed = instance.execute(
        scraper=scraper,
        collection_mode="api",
        run_id=run_id,
    )

    assert executed.run_id == run_id

    assert instance.runs.start_run.call_count == 2

    assert (
        instance.runs.start_run.call_args_list[0]
        == instance.runs.start_run.call_args_list[1]
    )

    scraper.run_with_result.assert_called_once()


def test_creation_mismatch_prevents_collection(
    recovery_orchestrator, run_id
):

    instance = recovery_orchestrator

    row = make_running_row(run_id)
    row["source_name"] = "bayt"

    instance.runs.start_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    instance.runs.get_run.return_value = row

    scraper = make_scraper(make_result(run_id))

    with pytest.raises(IngestionExecutionError) as caught:

        instance.execute(
            scraper=scraper,
            collection_mode="api",
            run_id=run_id,
        )

    assert caught.value.stage == "run_creation"

    assert isinstance(
        caught.value.__cause__,
        RunRecoveryError,
    )

    scraper.run_with_result.assert_not_called()

    instance.runs.start_run.assert_called_once()


def test_existing_run_not_adopted(
    recovery_orchestrator, run_id
):

    instance = recovery_orchestrator

    instance.runs.start_run.side_effect = (
        psycopg.errors.UniqueViolation()
    )

    scraper = make_scraper(make_result(run_id))

    with pytest.raises(IngestionExecutionError):

        instance.execute(
            scraper=scraper,
            collection_mode="api",
            run_id=run_id,
        )

    instance.runs.get_run.assert_not_called()

    scraper.run_with_result.assert_not_called()


def test_finalization_acknowledgement_recovery(
    recovery_orchestrator,
    run_id,
    opportunity,
    monkeypatch,
):

    instance = recovery_orchestrator

    row, connection, calculate = configure_finalization(
        instance,
        run_id,
        monkeypatch,
        received=2,
        inserted=1,
        invalid=1,
    )

    instance.runs.finish_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    result = make_result(
        run_id,
        (opportunity,),
        (make_rejection(run_id),),
    )

    executed = instance.persist_collection(result)

    assert executed.finalized_run == row
    assert executed.received == 2

    instance.runs.finish_run.assert_called_once()

    instance.opportunities.ingest.assert_called_once()

    instance.invalid_records.record.assert_called_once()

    calculate.assert_called_once_with(
        connection,
        run_id=run_id,
        received=2,
    )


def test_finalization_rollback_recovery(
    recovery_orchestrator,
    run_id,
    opportunity,
    monkeypatch,
):

    instance = recovery_orchestrator

    row, connection, calculate = configure_finalization(
        instance,
        run_id,
        monkeypatch,
        received=1,
        inserted=1,
    )

    connection.execute.return_value.fetchone.return_value = (
        make_running_row(run_id)
    )

    instance.runs.finish_run.side_effect = [
        psycopg.errors.ConnectionFailure(),
        row,
    ]

    executed = instance.persist_collection(
        make_result(run_id, (opportunity,))
    )

    assert executed.finalized_run == row

    assert instance.runs.finish_run.call_count == 2

    instance.opportunities.ingest.assert_called_once()

    calculate.assert_not_called()


def test_finalization_counter_mismatch(
    recovery_orchestrator,
    run_id,
    monkeypatch,
):

    instance = recovery_orchestrator

    row, _, _ = configure_finalization(
        instance,
        run_id,
        monkeypatch,
    )

    row["records_inserted"] = 1

    instance.runs.finish_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    result = make_result(run_id)

    with pytest.raises(IngestionExecutionError) as caught:

        instance.persist_collection(result)

    assert caught.value.stage == "finalization"

    assert caught.value.collection_result is result

    assert isinstance(
        caught.value.__cause__,
        RunRecoveryError,
    )

    instance.runs.finish_run.assert_called_once()


def test_run_validation_retry(
    recovery_orchestrator, run_id
):

    instance = recovery_orchestrator

    instance.runs.get_run.side_effect = [
        psycopg.errors.ConnectionFailure(),
        make_running_row(run_id),
    ]

    row = instance.validate_run(
        run_id=run_id,
        source_name="wuzzuf",
    )

    assert row["run_id"] == run_id

    assert instance.runs.get_run.call_count == 2


def test_permanent_validation_error(
    recovery_orchestrator, run_id
):

    instance = recovery_orchestrator

    instance.runs.get_run.side_effect = (
        psycopg.errors.InvalidPassword()
    )

    with pytest.raises(
        psycopg.errors.InvalidPassword
    ):

        instance.validate_run(
            run_id=run_id,
            source_name="wuzzuf",
        )

    instance.runs.get_run.assert_called_once()


def test_finalization_recovery_does_not_recollect(
    recovery_orchestrator,
    run_id,
    opportunity,
    monkeypatch,
):

    instance = recovery_orchestrator

    row, _, _ = configure_finalization(
        instance,
        run_id,
        monkeypatch,
        received=1,
        inserted=1,
    )

    instance.runs.finish_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    scraper = make_scraper(
        make_result(run_id, (opportunity,))
    )

    executed = instance.execute(
        scraper=scraper,
        collection_mode="api",
        run_id=run_id,
    )

    assert executed.finalized_run == row

    scraper.run_with_result.assert_called_once()

    instance.opportunities.ingest.assert_called_once()

    instance.runs.start_run.assert_called_once()

    instance.runs.finish_run.assert_called_once()
