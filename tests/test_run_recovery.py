from contextlib import nullcontext
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

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
    RunRecovery,
    RunRecoveryError,
)


@pytest.fixture
def run_id():

    return uuid4()


@pytest.fixture
def manager():

    return Mock()


@pytest.fixture
def recovery(manager):

    return RunRecovery(
        manager,
        RetryPolicy(initial_delay=0),
    )


@pytest.fixture
def creation_args(run_id):

    return {
        "run_id": run_id,
        "source_name": "wuzzuf",
        "collection_mode": "api",
        "collection_scope": "default",
        "metadata": {"max_jobs": 5},
    }


@pytest.fixture
def running_row(creation_args):

    return {
        **creation_args,
        "status": "running",
        "contract_version": CONTRACT_VERSION,
        "hash_version": HASH_VERSION,
        "started_at": datetime.now(timezone.utc),
        "finished_at": None,
        "error_message": None,
        **{
            f"records_{field}": 0
            for field in COUNTER_FIELDS
        },
    }


@pytest.fixture
def final_args(run_id):

    return {
        "run_id": run_id,
        "status": "completed",
        "received": 2,
        "error_message": None,
    }


@pytest.fixture
def final_row(running_row):

    return {
        **running_row,
        "status": "completed",
        "finished_at": datetime.now(timezone.utc),
        "records_received": 2,
        "records_inserted": 1,
        "records_invalid": 1,
    }


@pytest.fixture
def actual_counters():

    return RunCounters(
        received=2,
        inserted=1,
        updated=0,
        unchanged=0,
        invalid=1,
        stale=0,
        conflicted=0,
    )


@pytest.fixture
def database(manager, monkeypatch, actual_counters):

    connection = Mock()

    manager.storage.transaction.return_value = (
        nullcontext(connection)
    )

    calculate = Mock(
        return_value=actual_counters
    )

    monkeypatch.setattr(
        "scrapers.storage.run_recovery."
        "RunCounterRepository.calculate",
        calculate,
    )

    return connection, calculate


def test_normal_creation(
    recovery, manager, creation_args, run_id
):

    manager.start_run.return_value = run_id

    assert recovery.start_run(
        **creation_args
    ) == run_id

    manager.start_run.assert_called_once_with(
        **creation_args
    )

    manager.get_run.assert_not_called()


def test_creation_lost_acknowledgement(
    recovery, manager, creation_args, running_row, run_id
):

    manager.start_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    manager.get_run.return_value = running_row

    assert recovery.start_run(
        **creation_args
    ) == run_id

    manager.start_run.assert_called_once()
    manager.get_run.assert_called_once_with(run_id)


def test_creation_rolled_back(
    recovery, manager, creation_args, run_id
):

    manager.start_run.side_effect = [
        psycopg.errors.ConnectionFailure(),
        run_id,
    ]

    manager.get_run.return_value = None

    assert recovery.start_run(
        **creation_args
    ) == run_id

    assert manager.start_run.call_count == 2

    assert (
        manager.start_run.call_args_list[0]
        == manager.start_run.call_args_list[1]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", None),
        ("source_name", "bayt"),
        ("collection_mode", "html"),
        ("collection_scope", "different"),
        ("metadata", {}),
        ("contract_version", "0.0.0"),
        ("hash_version", 999),
        ("status", "completed"),
        ("records_received", 1),
        ("records_inserted", 1),
        ("started_at", None),
        ("error_message", "Unexpected error"),
    ],
)
def test_creation_mismatch(
    recovery, manager, creation_args,
    running_row, field, value
):

    running_row[field] = value

    manager.start_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    manager.get_run.return_value = running_row

    with pytest.raises(RunRecoveryError):

        recovery.start_run(**creation_args)

    manager.start_run.assert_called_once()


def test_existing_run_not_silently_adopted(
    recovery, manager, creation_args
):

    manager.start_run.side_effect = (
        psycopg.errors.UniqueViolation()
    )

    with pytest.raises(
        psycopg.errors.UniqueViolation
    ):

        recovery.start_run(**creation_args)

    manager.get_run.assert_not_called()


def test_creation_permanent_error(
    recovery, manager, creation_args
):

    manager.start_run.side_effect = (
        psycopg.errors.InvalidPassword()
    )

    with pytest.raises(
        psycopg.errors.InvalidPassword
    ):

        recovery.start_run(**creation_args)

    manager.start_run.assert_called_once()
    manager.get_run.assert_not_called()


def test_creation_verification_retry(
    recovery, manager, creation_args, running_row, run_id
):

    manager.start_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    manager.get_run.side_effect = [
        psycopg.errors.ConnectionFailure(),
        running_row,
    ]

    assert recovery.start_run(
        **creation_args
    ) == run_id

    manager.start_run.assert_called_once()

    assert manager.get_run.call_count == 2


def test_normal_finalization(
    recovery, manager, final_args, final_row
):

    manager.finish_run.return_value = final_row

    assert recovery.finish_run(
        **final_args
    ) == final_row

    manager.finish_run.assert_called_once_with(
        **final_args
    )

    manager.storage.transaction.assert_not_called()


def test_finalization_lost_acknowledgement(
    recovery, manager, final_args, final_row, database
):

    connection, calculate = database

    connection.execute.return_value.fetchone.return_value = (
        final_row
    )

    manager.finish_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    assert recovery.finish_run(
        **final_args
    ) == final_row

    manager.finish_run.assert_called_once()

    calculate.assert_called_once_with(
        connection,
        run_id=final_args["run_id"],
        received=2,
    )

    manager.storage.transaction.assert_called_once_with(
        read_only=True
    )


def test_finalization_rolled_back(
    recovery, manager, final_args,
    final_row, running_row, database
):

    connection, calculate = database

    connection.execute.return_value.fetchone.return_value = (
        running_row
    )

    manager.finish_run.side_effect = [
        psycopg.errors.ConnectionFailure(),
        final_row,
    ]

    assert recovery.finish_run(
        **final_args
    ) == final_row

    assert manager.finish_run.call_count == 2

    calculate.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", None),
        ("status", "failed"),
        ("records_received", 3),
        ("records_inserted", 2),
        ("records_updated", 1),
        ("records_unchanged", 1),
        ("records_invalid", 0),
        ("records_stale", 1),
        ("records_conflicted", 1),
        ("error_message", "Unexpected error"),
        ("contract_version", "0.0.0"),
        ("hash_version", 999),
        ("finished_at", None),
    ],
)
def test_finalization_mismatch(
    recovery, manager, final_args,
    final_row, database, field, value
):

    connection, _ = database

    final_row[field] = value

    connection.execute.return_value.fetchone.return_value = (
        final_row
    )

    manager.finish_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    with pytest.raises(RunRecoveryError):

        recovery.finish_run(**final_args)

    manager.finish_run.assert_called_once()


def test_missing_run_during_finalization(
    recovery, manager, final_args, database
):

    connection, _ = database

    connection.execute.return_value.fetchone.return_value = (
        None
    )

    manager.finish_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    with pytest.raises(RunRecoveryError):

        recovery.finish_run(**final_args)

    manager.finish_run.assert_called_once()


def test_finalization_permanent_error(
    recovery, manager, final_args
):

    manager.finish_run.side_effect = (
        psycopg.errors.CheckViolation()
    )

    with pytest.raises(
        psycopg.errors.CheckViolation
    ):

        recovery.finish_run(**final_args)

    manager.finish_run.assert_called_once()

    manager.storage.transaction.assert_not_called()


def test_finalization_verification_retry(
    recovery, manager, final_args, final_row, database
):

    connection, calculate = database

    connection.execute.side_effect = [
        psycopg.errors.ConnectionFailure(),
        Mock(
            **{"fetchone.return_value": final_row}
        ),
    ]

    manager.finish_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    assert recovery.finish_run(
        **final_args
    ) == final_row

    manager.finish_run.assert_called_once()

    assert connection.execute.call_count == 2

    calculate.assert_called_once()


def test_finalization_retry_exhaustion(
    recovery, manager, final_args,
    running_row, database
):

    connection, _ = database

    connection.execute.return_value.fetchone.return_value = (
        running_row
    )

    manager.finish_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    with pytest.raises(
        psycopg.errors.ConnectionFailure
    ):

        recovery.finish_run(**final_args)

    assert manager.finish_run.call_count == 3


@pytest.mark.parametrize(
    "status",
    ["partial", "failed", "aborted"],
)
def test_unsuccessful_finalization_recovery(
    recovery, manager, final_args,
    final_row, database, status
):

    connection, _ = database

    final_args["status"] = status

    final_args["error_message"] = (
        "Collection stopped: synthetic"
    )

    final_row["status"] = status

    final_row["error_message"] = (
        final_args["error_message"]
    )

    connection.execute.return_value.fetchone.return_value = (
        final_row
    )

    manager.finish_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    assert recovery.finish_run(
        **final_args
    ) == final_row

    manager.finish_run.assert_called_once()


def test_completed_unprocessed_records_rejected(
    recovery, manager, final_args, final_row, database
):

    connection, calculate = database

    final_row["records_invalid"] = 0

    calculate.return_value = RunCounters(
        received=2,
        inserted=1,
        updated=0,
        unchanged=0,
        invalid=0,
        stale=0,
        conflicted=0,
    )

    connection.execute.return_value.fetchone.return_value = (
        final_row
    )

    manager.finish_run.side_effect = (
        psycopg.errors.ConnectionFailure()
    )

    with pytest.raises(
        RunRecoveryError,
        match="unprocessed",
    ):

        recovery.finish_run(**final_args)
