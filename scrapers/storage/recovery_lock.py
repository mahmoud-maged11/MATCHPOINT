import hashlib

from contextlib import contextmanager
from uuid import UUID

from scrapers.storage.postgres import PostgresStorage

from scrapers.storage.connection_context import (
    bind_protected_connection,
)


class RecoveryLockError(RuntimeError):
    pass


class RecoveryAlreadyRunningError(RecoveryLockError):
    pass


class RecoveryLockManager:

    def __init__(self, storage: PostgresStorage):
        self.storage = storage

    @staticmethod
    def lock_key(run_id: UUID) -> int:

        if not isinstance(run_id, UUID):
            raise TypeError("run_id must be a UUID")

        digest = hashlib.sha256(
            b"matchpoint:recovery-lock:v1|"
            + run_id.bytes
        ).digest()

        return int.from_bytes(
            digest[:8],
            byteorder="big",
            signed=True,
        )

    @contextmanager
    def acquire(
        self,
        run_id: UUID,
        *,
        bind_connection: bool = False,
    ):

        key = self.lock_key(run_id)

        connection = self.storage.connect()

        try:

            connection.autocommit = True

            row = connection.execute(
                """
                SELECT pg_try_advisory_lock(
                    %s::bigint
                ) AS acquired
                """,
                (key,),
            ).fetchone()

            if not row or not row["acquired"]:
                raise RecoveryAlreadyRunningError(
                    f"Recovery lock unavailable: {run_id}"
                )

            if bind_connection:

                with bind_protected_connection(
                    storage=self.storage,
                    connection=connection,
                    run_id=run_id,
                ):
                    yield

            else:
                yield

        finally:
            connection.close()