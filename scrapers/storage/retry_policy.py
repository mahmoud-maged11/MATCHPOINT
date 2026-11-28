from dataclasses import dataclass
from time import sleep
from typing import Callable, TypeVar

import psycopg


T = TypeVar("T")


RETRYABLE_SQLSTATES = frozenset({
    "08000",
    "08001",
    "08003",
    "08006",
    "08007",
    "40001",
    "40P01",
    "55P03",
    "57P01",
    "57P02",
    "57P03",
})


TRANSIENT_CONNECTION_MESSAGES = (
    "connection refused",
    "connection reset",
    "connection timed out",
    "timeout expired",
    "server closed the connection unexpectedly",
    "connection is closed",
    "connection is lost",
    "consuming input failed",
    "sending query failed",
    "broken pipe",
    "network is unreachable",
)


PERMANENT_CONNECTION_MESSAGES = (
    "password authentication failed",
    "authentication failed",
    "no password supplied",
    "no pg_hba.conf entry",
    "does not exist",
    "permission denied",
    "certificate",
    "could not translate host name",
    "invalid connection option",
)


def is_retryable_database_error(
    error: BaseException,
) -> bool:

    if not isinstance(error, psycopg.Error):
        return False

    sqlstate = error.sqlstate

    if sqlstate is not None:

        return sqlstate in RETRYABLE_SQLSTATES

    if not isinstance(
        error,
        psycopg.OperationalError,
    ):

        return False

    message = str(error).casefold()

    if any(
        marker in message
        for marker in PERMANENT_CONNECTION_MESSAGES
    ):

        return False

    return any(
        marker in message
        for marker in TRANSIENT_CONNECTION_MESSAGES
    )


@dataclass(frozen=True, slots=True)
class RetryPolicy:

    max_attempts: int = 3
    initial_delay: float = 1.0

    def __post_init__(self):

        import math

        if (
            type(self.max_attempts) is not int
            or not 1 <= self.max_attempts <= 3
        ):

            raise ValueError(
                "max_attempts must be between 1 and 3"
            )

        if (
            type(self.initial_delay) not in (int, float)
            or not math.isfinite(self.initial_delay)
            or self.initial_delay < 0
        ):

            raise ValueError(
                "initial_delay must be finite and non-negative"
            )

    def execute(
        self,
        operation: Callable[[], T],
        *,
        sleeper: Callable[[float], None] = sleep,
    ) -> T:

        if not callable(operation):
            raise TypeError("operation must be callable")

        if not callable(sleeper):
            raise TypeError("sleeper must be callable")

        for attempt in range(
            1,
            self.max_attempts + 1,
        ):

            try:

                return operation()

            except psycopg.Error as error:

                if (
                    not is_retryable_database_error(error)
                    or attempt == self.max_attempts
                ):

                    raise

                delay = (
                    self.initial_delay
                    * 2 ** (attempt - 1)
                )

                sleeper(delay)

        raise RuntimeError(
            "Unreachable retry state"
        )
