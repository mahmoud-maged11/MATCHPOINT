from unittest.mock import Mock
from uuid import uuid4

import psycopg
import pytest

from scrapers.storage.orchestrator import (
    IngestionExecutionError,
)

from test_incremental_pipeline import pipeline


def failure(run_id, cause):

    error = IngestionExecutionError(
        run_id=run_id,
        stage="accepted_persistence",
    )

    error.__cause__ = cause

    return error


@pytest.mark.parametrize(
    "cause",
    [
        psycopg.errors.ConnectionFailure("lost"),
        psycopg.errors.AdminShutdown("terminated"),
        psycopg.OperationalError("connection reset"),
        psycopg.errors.DeadlockDetected("deadlock"),
    ],
)
def test_recovery_retries(
    pipeline,
    monkeypatch,
    cause,
):

    orchestrator = pipeline["orchestrator"]
    run_id = pipeline["run_id"]

    expected = object()

    recover = Mock(
        side_effect=[
            failure(run_id, cause),
            expected,
        ]
    )

    monkeypatch.setattr(
        orchestrator,
        "recover",
        recover,
    )

    monkeypatch.setattr(
        "time.sleep",
        Mock(),
    )

    assert orchestrator.recover_with_retry(
        run_id=run_id
    ) is expected

    assert recover.call_count == 2

    for call in recover.call_args_list:

        assert call.kwargs == {
            "run_id": run_id,
        }


@pytest.mark.parametrize(
    "cause",
    [
        ValueError("invalid data"),
        RuntimeError("programming error"),
        psycopg.errors.UniqueViolation("duplicate"),
        psycopg.OperationalError(
            "password authentication failed"
        ),
    ],
)
def test_permanent_error_not_retried(
    pipeline,
    monkeypatch,
    cause,
):

    orchestrator = pipeline["orchestrator"]
    run_id = pipeline["run_id"]

    recover = Mock(
        side_effect=failure(run_id, cause)
    )

    monkeypatch.setattr(
        orchestrator,
        "recover",
        recover,
    )

    with pytest.raises(IngestionExecutionError):

        orchestrator.recover_with_retry(
            run_id=run_id
        )

    recover.assert_called_once()


def test_retry_limit(pipeline, monkeypatch):

    orchestrator = pipeline["orchestrator"]
    run_id = pipeline["run_id"]

    recover = Mock(
        side_effect=failure(
            run_id,
            psycopg.errors.ConnectionFailure("lost"),
        )
    )

    sleeper = Mock()

    monkeypatch.setattr(
        orchestrator,
        "recover",
        recover,
    )

    monkeypatch.setattr(
        "time.sleep",
        sleeper,
    )

    with pytest.raises(IngestionExecutionError):

        orchestrator.recover_with_retry(
            run_id=run_id
        )

    attempts = orchestrator.retry_policy.max_attempts

    assert recover.call_count == attempts
    assert sleeper.call_count == attempts - 1


def test_recovery_success_without_retry(
    pipeline,
    monkeypatch,
):

    orchestrator = pipeline["orchestrator"]
    run_id = pipeline["run_id"]

    expected = object()

    recover = Mock(return_value=expected)

    monkeypatch.setattr(
        orchestrator,
        "recover",
        recover,
    )

    assert orchestrator.recover_with_retry(
        run_id=run_id
    ) is expected

    recover.assert_called_once_with(
        run_id=run_id
    )
