from unittest.mock import Mock

import psycopg
import pytest

from scrapers.storage.retry_policy import (
    RetryPolicy,
    is_retryable_database_error,
)


@pytest.mark.parametrize(
    "error",
    [
        psycopg.errors.DeadlockDetected(),
        psycopg.errors.SerializationFailure(),
        psycopg.errors.LockNotAvailable(),
        psycopg.errors.ConnectionFailure(),
        psycopg.errors.AdminShutdown(),
        psycopg.errors.CrashShutdown(),
        psycopg.errors.CannotConnectNow(),
    ],
)
def test_retryable_sqlstates(error):

    assert is_retryable_database_error(error)


@pytest.mark.parametrize(
    "error",
    [
        psycopg.errors.InvalidPassword(),
        psycopg.errors.InvalidAuthorizationSpecification(),
        psycopg.errors.UniqueViolation(),
        psycopg.errors.ForeignKeyViolation(),
        psycopg.errors.CheckViolation(),
        psycopg.errors.UndefinedTable(),
        psycopg.errors.SyntaxError(),
        psycopg.errors.QueryCanceled(),
        ValueError("Invalid source identity"),
        RuntimeError("Unexpected failure"),
        ConnectionError("Unclassified connection error"),
    ],
)
def test_permanent_errors(error):

    assert not is_retryable_database_error(error)


@pytest.mark.parametrize(
    "message",
    [
        "Connection refused",
        "Connection reset by peer",
        "Connection timed out",
        "timeout expired",
        "server closed the connection unexpectedly",
        "connection is closed",
        "Broken pipe",
        "Network is unreachable",
    ],
)
def test_transient_connection_messages(message):

    error = psycopg.OperationalError(message)

    assert is_retryable_database_error(error)


@pytest.mark.parametrize(
    "message",
    [
        "password authentication failed",
        "no pg_hba.conf entry",
        "database does not exist",
        "permission denied",
        "certificate verification failed",
        "could not translate host name",
        "invalid connection option",
        "Unknown operational failure",
        "connection refused; password authentication failed",
    ],
)
def test_non_retryable_connection_messages(message):

    error = psycopg.OperationalError(message)

    assert not is_retryable_database_error(error)


def test_success_without_retry():

    operation = Mock(return_value="success")
    sleeper = Mock()

    result = RetryPolicy().execute(
        operation,
        sleeper=sleeper,
    )

    assert result == "success"

    operation.assert_called_once()
    sleeper.assert_not_called()


def test_retry_then_success():

    operation = Mock(
        side_effect=[
            psycopg.errors.DeadlockDetected(),
            "success",
        ]
    )

    sleeper = Mock()

    result = RetryPolicy().execute(
        operation,
        sleeper=sleeper,
    )

    assert result == "success"
    assert operation.call_count == 2

    sleeper.assert_called_once_with(1.0)


def test_exponential_backoff():

    operation = Mock(
        side_effect=[
            psycopg.errors.DeadlockDetected(),
            psycopg.errors.SerializationFailure(),
            "success",
        ]
    )

    sleeper = Mock()

    result = RetryPolicy().execute(
        operation,
        sleeper=sleeper,
    )

    assert result == "success"
    assert operation.call_count == 3

    assert [
        call.args[0]
        for call in sleeper.call_args_list
    ] == [1.0, 2.0]


def test_retry_exhaustion():

    final_error = psycopg.errors.ConnectionFailure()

    operation = Mock(
        side_effect=[
            psycopg.errors.ConnectionFailure(),
            psycopg.errors.ConnectionFailure(),
            final_error,
        ]
    )

    sleeper = Mock()

    with pytest.raises(
        psycopg.errors.ConnectionFailure
    ) as caught:

        RetryPolicy().execute(
            operation,
            sleeper=sleeper,
        )

    assert caught.value is final_error
    assert operation.call_count == 3
    assert sleeper.call_count == 2


def test_permanent_failure_not_retried():

    operation = Mock(
        side_effect=psycopg.errors.InvalidPassword()
    )

    sleeper = Mock()

    with pytest.raises(
        psycopg.errors.InvalidPassword
    ):

        RetryPolicy().execute(
            operation,
            sleeper=sleeper,
        )

    operation.assert_called_once()
    sleeper.assert_not_called()


def test_unexpected_error_not_retried():

    operation = Mock(
        side_effect=RuntimeError("Programming error")
    )

    sleeper = Mock()

    with pytest.raises(RuntimeError):

        RetryPolicy().execute(
            operation,
            sleeper=sleeper,
        )

    operation.assert_called_once()
    sleeper.assert_not_called()


def test_permanent_failure_after_transient_failure():

    operation = Mock(
        side_effect=[
            psycopg.errors.DeadlockDetected(),
            psycopg.errors.UniqueViolation(),
        ]
    )

    sleeper = Mock()

    with pytest.raises(
        psycopg.errors.UniqueViolation
    ):

        RetryPolicy().execute(
            operation,
            sleeper=sleeper,
        )

    assert operation.call_count == 2
    sleeper.assert_called_once_with(1.0)


def test_keyboard_interrupt_not_retried():

    operation = Mock(
        side_effect=KeyboardInterrupt()
    )

    sleeper = Mock()

    with pytest.raises(KeyboardInterrupt):

        RetryPolicy().execute(
            operation,
            sleeper=sleeper,
        )

    operation.assert_called_once()
    sleeper.assert_not_called()


def test_single_attempt_policy():

    operation = Mock(
        side_effect=psycopg.errors.ConnectionFailure()
    )

    sleeper = Mock()

    with pytest.raises(
        psycopg.errors.ConnectionFailure
    ):

        RetryPolicy(
            max_attempts=1,
        ).execute(
            operation,
            sleeper=sleeper,
        )

    operation.assert_called_once()
    sleeper.assert_not_called()


@pytest.mark.parametrize(
    "attempts",
    [0, -1, 4, True, 2.5, "3"],
)
def test_invalid_attempts(attempts):

    with pytest.raises(ValueError):

        RetryPolicy(max_attempts=attempts)


@pytest.mark.parametrize(
    "delay",
    [-1, True, "1", float("nan"), float("inf")],
)
def test_invalid_delay(delay):

    with pytest.raises(ValueError):

        RetryPolicy(initial_delay=delay)


def test_original_arguments_preserved():

    payload = {"id": "ABC123"}
    run_id = object()

    operation = Mock(
        side_effect=[
            psycopg.errors.ConnectionFailure(),
            "success",
        ]
    )

    result = RetryPolicy().execute(
        lambda: operation(payload, run_id),
        sleeper=Mock(),
    )

    assert result == "success"

    for call in operation.call_args_list:

        assert call.args[0] is payload
        assert call.args[1] is run_id


def test_invalid_operation():

    with pytest.raises(TypeError):

        RetryPolicy().execute(None)


def test_invalid_sleeper():

    with pytest.raises(TypeError):

        RetryPolicy().execute(
            lambda: None,
            sleeper=None,
        )
