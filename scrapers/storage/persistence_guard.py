from __future__ import annotations

from contextlib import contextmanager

from scrapers.storage.concurrency import WAREHOUSE_KEY

from scrapers.storage.connection_context import (
    get_protected_connection,
    ProtectedConnectionError,
    ProtectedConnectionLostError,
)


@contextmanager
def persistence_guard(storage, run_id):

    protected = get_protected_connection()

    if protected is None:
        raise ProtectedConnectionError(
            "Persistence guard requires a protected connection"
        )

    if (
        protected.storage is not storage
        or protected.run_id != run_id
    ):
        raise ProtectedConnectionError(
            "Persistence guard identity mismatch"
        )

    connection = protected.connection

    if connection.closed or connection.broken:
        raise ProtectedConnectionLostError(
            "Persistence connection unavailable"
        )

    if not connection.autocommit:
        raise ProtectedConnectionError(
            "Persistence guard requires autocommit"
        )

    import time
    from psycopg.errors import LockNotAvailable

    deadline = time.monotonic() + 30.0

    while True:

        if connection.closed or connection.broken:
            raise ProtectedConnectionLostError(
                "Persistence connection lost while waiting"
            )

        row = connection.execute(
            "SELECT pg_try_advisory_lock_shared(%s::bigint) AS acquired",
            (WAREHOUSE_KEY,),
        ).fetchone()

        if row["acquired"]:
            break

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            raise LockNotAvailable(
                "Warehouse persistence lock acquisition timed out"
            )

        time.sleep(min(0.1, remaining))

    try:

        yield connection

        if connection.closed or connection.broken:
            raise ProtectedConnectionLostError(
                "Persistence connection lost"
            )

    finally:

        if not connection.closed and not connection.broken:

            row = connection.execute(
                "SELECT pg_advisory_unlock_shared(%s::bigint) AS released",
                (WAREHOUSE_KEY,),
            ).fetchone()

            if not row or not row["released"]:
                raise ProtectedConnectionError(
                    "Persistence guard ownership lost"
                )
