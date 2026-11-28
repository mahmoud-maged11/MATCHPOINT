from unittest.mock import Mock

import psycopg
import pytest

from scrapers.storage.connection_context import (
    ProtectedConnectionError,
    ProtectedConnectionLostError,
    get_protected_connection,
)

from scrapers.storage.orchestrator import (
    IngestionExecutionError,
    IngestionOrchestrator,
)

from test_incremental_pipeline import (
    pipeline,
    make_scraper,
)

from test_connection_failure_recovery import (
    terminate_protected_backend,
    assert_recovered,
)


@pytest.mark.parametrize(
    "cause,expected",
    [
        (
            ProtectedConnectionLostError("lost"),
            True,
        ),
        (
            ProtectedConnectionError("identity mismatch"),
            False,
        ),
        (
            psycopg.OperationalError("connection reset"),
            True,
        ),
        (
            psycopg.OperationalError(
                "password authentication failed"
            ),
            False,
        ),
        (
            ValueError("invalid data"),
            False,
        ),
    ],
)
def test_failure_classification(cause, expected):

    assert (
        IngestionOrchestrator.is_recoverable_failure(
            cause
        ) is expected
    )


def test_identity_error_overrides_transient_cause():

    error = ProtectedConnectionError(
        "Protected storage identity mismatch"
    )

    error.__cause__ = (
        psycopg.errors.ConnectionFailure("lost")
    )

    assert not (
        IngestionOrchestrator.is_recoverable_failure(
            error
        )
    )


@pytest.mark.parametrize(
    "failure_point",
    [
        "before_commit",
        "after_commit",
        "after_finalization",
        "closed_protected_connection",
    ],
)
def test_automatic_real_connection_recovery(
    pipeline,
    monkeypatch,
    failure_point,
):

    orchestrator = pipeline["orchestrator"]
    storage = orchestrator.storage
    run_id = pipeline["run_id"]

    orchestrator.batch_size = 2

    scraper = make_scraper()

    collect = Mock(wraps=orchestrator.collect)

    monkeypatch.setattr(
        orchestrator,
        "collect",
        collect,
    )

    if failure_point == "before_commit":

        owner = orchestrator.opportunities
        method = "_insert_observation"

    elif failure_point == "after_finalization":

        owner = orchestrator.runs
        method = "finish_run"

    else:

        owner = orchestrator.opportunities
        method = "ingest_many"

    original = getattr(owner, method)

    terminated = False

    def interrupt(*args, **kwargs):

        nonlocal terminated

        result = original(*args, **kwargs)

        if not terminated:

            terminated = True

            terminate_protected_backend(
                storage,
                run_id,
            )

            protected = get_protected_connection()

            if (
                failure_point
                == "closed_protected_connection"
            ):

                protected.connection.close()

                with storage.transaction():

                    pytest.fail(
                        "Lost protected connection reused"
                    )

            else:

                protected.connection.execute(
                    "SELECT 1"
                )

        return result

    monkeypatch.setattr(
        owner,
        method,
        interrupt,
    )

    recovered = orchestrator.execute_with_recovery(
        scraper=scraper,
        collection_mode="api",
        collection_scope="jobs",
        run_id=run_id,
        checkpoint_intent=pipeline["intent"],
    )

    assert terminated

    collect.assert_called_once()

    assert get_protected_connection() is None

    assert_recovered(
        pipeline,
        recovered,
    )

    repeated = orchestrator.recover_with_retry(
        run_id=run_id
    )

    assert repeated.already_finalized

    assert (
        repeated.finalized_run
        == recovered.finalized_run
    )


@pytest.mark.parametrize(
    "stage,cause",
    [
        (
            "collection",
            psycopg.errors.ConnectionFailure("lost"),
        ),
        (
            "checkpoint_coverage",
            psycopg.errors.ConnectionFailure("lost"),
        ),
        (
            "run_creation",
            psycopg.errors.ConnectionFailure("lost"),
        ),
        (
            "accepted_persistence",
            ValueError("invalid data"),
        ),
        (
            "accepted_persistence",
            ProtectedConnectionError("identity mismatch"),
        ),
    ],
)
def test_unsafe_automatic_recovery_is_rejected(
    pipeline,
    monkeypatch,
    stage,
    cause,
):

    orchestrator = pipeline["orchestrator"]

    error = IngestionExecutionError(
        run_id=pipeline["run_id"],
        stage=stage,
    )

    error.__cause__ = cause

    execute = Mock(side_effect=error)
    recover = Mock()

    monkeypatch.setattr(
        orchestrator,
        "execute",
        execute,
    )

    monkeypatch.setattr(
        orchestrator,
        "recover_with_retry",
        recover,
    )

    with pytest.raises(IngestionExecutionError):

        orchestrator.execute_with_recovery(
            run_id=pipeline["run_id"]
        )

    execute.assert_called_once()

    recover.assert_not_called()
