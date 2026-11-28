from unittest.mock import Mock

import psycopg
import pytest

from scrapers.storage.retry_policy import RetryPolicy

from scrapers.storage.orchestrator import (
    IngestionOrchestrator,
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
def fast_retry(orchestrator):

    orchestrator.retry_policy = RetryPolicy(
        max_attempts=3,
        initial_delay=0,
    )

    return orchestrator


def test_default_retry_policy():

    instance = IngestionOrchestrator(Mock())

    assert isinstance(
        instance.retry_policy,
        RetryPolicy,
    )

    assert instance.retry_policy.max_attempts == 3
    assert instance.retry_policy.initial_delay == 1


def test_custom_retry_policy():

    policy = RetryPolicy(
        max_attempts=1,
        initial_delay=0,
    )

    instance = IngestionOrchestrator(
        Mock(),
        retry_policy=policy,
    )

    assert instance.retry_policy is policy


def test_invalid_retry_policy():

    with pytest.raises(TypeError):

        IngestionOrchestrator(
            Mock(),
            retry_policy="invalid",
        )


@pytest.mark.parametrize(
    "error",
    [
        psycopg.errors.DeadlockDetected(),
        psycopg.errors.SerializationFailure(),
        psycopg.errors.LockNotAvailable(),
        psycopg.errors.ConnectionFailure(),
    ],
)
def test_accepted_retry(
    fast_retry,
    run_id,
    opportunity,
    error,
):

    repository = fast_retry.opportunities

    outcome = Mock()
    outcome.outcome = "inserted"

    repository.ingest.side_effect = [
        error,
        outcome,
    ]

    result = fast_retry.persist_accepted(
        make_result(run_id, (opportunity,))
    )

    assert result.received == 1
    assert repository.ingest.call_count == 2

    assert (
        repository.ingest.call_args_list[0]
        == repository.ingest.call_args_list[1]
    )


def test_accepted_lost_acknowledgement(
    fast_retry,
    run_id,
    opportunity,
):

    outcome = Mock()
    outcome.outcome = "duplicate"
    outcome.original_outcome = "inserted"

    fast_retry.opportunities.ingest.side_effect = [
        psycopg.errors.ConnectionFailure(),
        outcome,
    ]

    result = fast_retry.persist_collection(
        make_result(run_id, (opportunity,))
    )

    assert result.received == 1

    fast_retry.runs.finish_run.assert_called_once_with(
        run_id=run_id,
        status="completed",
        received=1,
        error_message=None,
    )


def test_accepted_retry_exhaustion(
    fast_retry,
    run_id,
    opportunity,
):

    fast_retry.opportunities.ingest.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    result = make_result(
        run_id,
        (opportunity,),
    )

    with pytest.raises(IngestionExecutionError) as caught:

        fast_retry.persist_collection(result)

    assert caught.value.stage == "accepted_persistence"
    assert caught.value.collection_result is result

    assert (
        fast_retry.opportunities.ingest.call_count
        == 3
    )

    fast_retry.runs.finish_run.assert_not_called()


def test_permanent_accepted_failure(
    fast_retry,
    run_id,
    opportunity,
):

    fast_retry.opportunities.ingest.side_effect = (
        psycopg.errors.UniqueViolation()
    )

    with pytest.raises(IngestionExecutionError):

        fast_retry.persist_collection(
            make_result(run_id, (opportunity,))
        )

    fast_retry.opportunities.ingest.assert_called_once()
    fast_retry.runs.finish_run.assert_not_called()


def test_rejected_retry(
    fast_retry,
    run_id,
):

    repository = fast_retry.invalid_records

    outcome = repository.record.return_value

    repository.record.side_effect = [
        psycopg.errors.ConnectionFailure(),
        outcome,
    ]

    result = fast_retry.persist_rejected(
        make_result(
            run_id,
            rejected=(make_rejection(run_id),),
        )
    )

    assert result.received == 1
    assert repository.record.call_count == 2

    assert (
        repository.record.call_args_list[0]
        == repository.record.call_args_list[1]
    )


def test_rejected_retry_exhaustion(
    fast_retry,
    run_id,
):

    fast_retry.invalid_records.record.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    result = make_result(
        run_id,
        rejected=(make_rejection(run_id),),
    )

    with pytest.raises(IngestionExecutionError) as caught:

        fast_retry.persist_collection(result)

    assert caught.value.stage == "rejected_persistence"
    assert caught.value.collection_result is result

    assert (
        fast_retry.invalid_records.record.call_count
        == 3
    )

    fast_retry.runs.finish_run.assert_not_called()


def test_permanent_rejected_failure(
    fast_retry,
    run_id,
):

    fast_retry.invalid_records.record.side_effect = (
        psycopg.errors.InvalidPassword()
    )

    with pytest.raises(IngestionExecutionError):

        fast_retry.persist_collection(
            make_result(
                run_id,
                rejected=(make_rejection(run_id),),
            )
        )

    fast_retry.invalid_records.record.assert_called_once()


def test_storage_retry_does_not_recollect(
    fast_retry,
    run_id,
    opportunity,
):

    outcome = Mock()
    outcome.outcome = "inserted"

    fast_retry.opportunities.ingest.side_effect = [
        psycopg.errors.DeadlockDetected(),
        outcome,
    ]

    scraper = make_scraper(
        make_result(run_id, (opportunity,))
    )

    executed = fast_retry.execute(
        scraper=scraper,
        collection_mode="api",
        run_id=run_id,
    )

    assert executed.received == 1

    scraper.run_with_result.assert_called_once_with(
        run_id=run_id,
    )

    fast_retry.runs.start_run.assert_called_once()
    fast_retry.runs.finish_run.assert_called_once()

    assert (
        fast_retry.opportunities.ingest.call_count
        == 2
    )


def test_only_failed_observation_is_retried(
    fast_retry,
    run_id,
    opportunity,
):

    second = opportunity.model_copy(
        update={
            "source_opportunity_id": "XYZ456",
            "title": "Second synthetic opportunity",
        }
    )

    outcome = Mock()
    outcome.outcome = "inserted"

    repository = fast_retry.opportunities

    repository.ingest.side_effect = [
        outcome,
        psycopg.errors.ConnectionFailure(),
        outcome,
    ]

    result = fast_retry.persist_collection(
        make_result(
            run_id,
            (opportunity, second),
        )
    )

    assert result.received == 2
    assert repository.ingest.call_count == 3

    calls = repository.ingest.call_args_list

    assert calls[0] != calls[1]
    assert calls[1] == calls[2]


def test_rejection_retry_does_not_repeat_accepted(
    fast_retry,
    run_id,
    opportunity,
):

    repository = fast_retry.invalid_records

    outcome = repository.record.return_value

    repository.record.side_effect = [
        psycopg.errors.ConnectionFailure(),
        outcome,
    ]

    result = fast_retry.persist_collection(
        make_result(
            run_id,
            (opportunity,),
            (make_rejection(run_id),),
        )
    )

    assert result.received == 2

    fast_retry.opportunities.ingest.assert_called_once()

    assert repository.record.call_count == 2

    fast_retry.runs.finish_run.assert_called_once()


def test_finalization_not_blindly_retried_with_single_attempt(
    fast_retry,
    run_id,
):

    fast_retry.retry_policy = RetryPolicy(
        max_attempts=1,
        initial_delay=0,
    )


    fast_retry.runs.finish_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    with pytest.raises(IngestionExecutionError) as caught:

        fast_retry.persist_collection(
            make_result(run_id)
        )

    assert caught.value.stage == "finalization"

    fast_retry.runs.finish_run.assert_called_once()


def test_run_creation_not_blindly_retried_with_single_attempt(
    fast_retry,
    run_id,
):

    fast_retry.retry_policy = RetryPolicy(
        max_attempts=1,
        initial_delay=0,
    )


    fast_retry.runs.start_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    scraper = make_scraper(
        make_result(run_id)
    )

    with pytest.raises(IngestionExecutionError) as caught:

        fast_retry.execute(
            scraper=scraper,
            collection_mode="api",
            run_id=run_id,
        )

    assert caught.value.stage == "run_creation"

    fast_retry.runs.start_run.assert_called_once()
    scraper.run_with_result.assert_not_called()
