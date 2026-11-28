"""Cooperative PostgreSQL concurrency protection."""

from __future__ import annotations

import hashlib
import json
import math
import time

from contextlib import contextmanager, ExitStack


SUPPORTED_SOURCES = frozenset({
    "egyincs",
    "wuzzuf",
    "forasna",
    "devpost",
    "un_volunteers",
    "itida",
    "nti",
    "bayt",
})


class ConcurrencyError(RuntimeError):
    """Base concurrency protection error."""


class LockUnavailableError(ConcurrencyError):
    """Requested lock could not be acquired."""


class LockConnectionLostError(ConcurrencyError):
    """The connection protecting a lock was lost."""


def lock_key(namespace, *parts):

    payload = json.dumps(
        [namespace, *parts],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return int.from_bytes(
        hashlib.sha256(payload).digest()[:8],
        byteorder="big",
        signed=True,
    )


NAMESPACE = "matchpoint.concurrency.v1"

WAREHOUSE_KEY = lock_key(
    NAMESPACE,
    "warehouse",
)


class ConcurrencyManager:

    def __init__(
        self,
        connection_factory,
        *,
        timeout=0,
        poll_interval=0.1,
    ):

        for name, value in (
            ("timeout", timeout),
            ("poll_interval", poll_interval),
        ):

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(
                    f"Invalid {name}"
                )

        if timeout < 0:
            raise ValueError(
                "timeout must be nonnegative"
            )

        if poll_interval <= 0:
            raise ValueError(
                "poll_interval must be positive"
            )

        self.connection_factory = connection_factory
        self.timeout = timeout
        self.poll_interval = poll_interval

    @staticmethod
    def ensure_connection(connection):

        if connection.closed or connection.broken:

            raise LockConnectionLostError(
                "Lock connection is unavailable"
            )

    @contextmanager
    def _session(self):

        connection = self.connection_factory()

        try:

            self.ensure_connection(connection)

            if not connection.autocommit:

                raise ConcurrencyError(
                    "Lock connection must use autocommit"
                )

            yield connection

        finally:

            connection.close()

    @contextmanager
    def _lock(
        self,
        connection,
        key,
        *,
        shared=False,
        label="lock",
    ):

        acquire_sql = (
            "SELECT pg_try_advisory_lock_shared(%s)"
            if shared else
            "SELECT pg_try_advisory_lock(%s)"
        )

        release_sql = (
            "SELECT pg_advisory_unlock_shared(%s)"
            if shared else
            "SELECT pg_advisory_unlock(%s)"
        )

        deadline = time.monotonic() + self.timeout

        while True:

            self.ensure_connection(connection)

            acquired = connection.execute(
                acquire_sql,
                (key,),
            ).fetchone()[0]

            if acquired:
                break

            remaining = deadline - time.monotonic()

            if remaining <= 0:

                raise LockUnavailableError(
                    f"Lock unavailable: {label}"
                )

            time.sleep(
                min(
                    self.poll_interval,
                    remaining,
                )
            )

        try:

            yield connection

        finally:

            if not connection.closed and not connection.broken:

                released = connection.execute(
                    release_sql,
                    (key,),
                ).fetchone()[0]

                if not released:

                    raise ConcurrencyError(
                        f"Lock ownership lost: {label}"
                    )

    @staticmethod
    def validate_scope(source, scope):

        if source not in SUPPORTED_SOURCES:

            raise ValueError(
                f"Unsupported source: {source}"
            )

        if source == "egyincs":

            if scope not in {
                "all",
                "jobs",
                "lp_course",
            }:

                raise ValueError(
                    f"Invalid Egyincs scope: {scope}"
                )

        elif scope != "default":

            raise ValueError(
                f"Invalid scope for {source}: {scope}"
            )

    @contextmanager
    def source(self, source, scope="default"):

        self.validate_scope(source, scope)

        source_gate = lock_key(
            NAMESPACE,
            "source_gate",
            source,
        )

        with self._session() as connection:

            with ExitStack() as stack:

                if source == "egyincs":

                    stack.enter_context(
                        self._lock(
                            connection,
                            source_gate,
                            shared=scope != "all",
                            label=f"{source}:gate",
                        )
                    )

                    if scope != "all":

                        endpoint_key = lock_key(
                            NAMESPACE,
                            "source",
                            source,
                            scope,
                        )

                        stack.enter_context(
                            self._lock(
                                connection,
                                endpoint_key,
                                label=f"{source}:{scope}",
                            )
                        )

                else:

                    stack.enter_context(
                        self._lock(
                            connection,
                            lock_key(
                                NAMESPACE,
                                "source",
                                source,
                                scope,
                            ),
                            label=f"{source}:{scope}",
                        )
                    )

                yield connection

    @contextmanager
    def ingestion(self):

        with self._session() as connection:

            with self._lock(
                connection,
                WAREHOUSE_KEY,
                shared=True,
                label="warehouse:ingestion",
            ):

                yield connection

    @contextmanager
    def warehouse(self):

        with self._session() as connection:

            with self._lock(
                connection,
                WAREHOUSE_KEY,
                shared=False,
                label="warehouse:exclusive",
            ):

                yield connection
