import os
import time

from uuid import uuid4
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor

import pytest
from psycopg.errors import LockNotAvailable

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.recovery_lock import (
    RecoveryLockManager,
)

from scrapers.storage.persistence_guard import (
    persistence_guard,
)

from scrapers.storage.concurrency import WAREHOUSE_KEY


pytestmark = pytest.mark.skipif(
    os.environ.get(
        "MATCHPOINT_RUN_CONCURRENCY_TESTS"
    ) != "1",
    reason="Requires isolated PostgreSQL database",
)


@pytest.fixture
def storage():

    instance = PostgresStorage(
        PostgresSettings(
            host="127.0.0.1",
            port=5432,
            database="matchpoint_ingestion_test",
            user="matchpoint",
            password=os.environ["POSTGRES_PASSWORD"],
        )
    )

    with instance.transaction(read_only=True) as connection:

        row = connection.execute(
            "SELECT current_database() AS database, "
            "system_identifier::text AS cluster "
            "FROM pg_control_system()"
        ).fetchone()

        assert row == {
            "database": "matchpoint_ingestion_test",
            "cluster": "7711828057299574822",
        }

    return instance


def test_parallel_lock_timeout_and_recovery(storage):

    barrier = Barrier(3, timeout=10)

    def transaction_worker():

        barrier.wait()

        started = time.monotonic()

        with pytest.raises(LockNotAvailable) as error:

            with storage.transaction():

                pytest.fail(
                    "Write transaction bypassed warehouse lock"
                )

        elapsed = time.monotonic() - started

        assert error.value.sqlstate == "55P03"
        assert 29 <= elapsed <= 40, elapsed

        return elapsed

    def persistence_worker():

        run_id = uuid4()

        with RecoveryLockManager(storage).acquire(
            run_id,
            bind_connection=True,
        ):

            barrier.wait()

            started = time.monotonic()

            with pytest.raises(LockNotAvailable) as error:

                with persistence_guard(storage, run_id):

                    pytest.fail(
                        "Persistence bypassed warehouse lock"
                    )

            elapsed = time.monotonic() - started

            assert error.value.sqlstate == "55P03"
            assert 29 <= elapsed <= 40, elapsed

            with storage.transaction(
                read_only=True
            ) as connection:

                assert connection.execute(
                    "SELECT 1 AS value"
                ).fetchone()["value"] == 1

            return elapsed

    observer = storage.connect()
    observer.autocommit = True

    try:

        assert observer.execute(
            "SELECT pg_try_advisory_lock(%s::bigint) AS acquired",
            (WAREHOUSE_KEY,),
        ).fetchone()["acquired"]

        with ThreadPoolExecutor(max_workers=2) as pool:

            transaction = pool.submit(transaction_worker)
            persistence = pool.submit(persistence_worker)

            barrier.wait()

            transaction_elapsed = transaction.result(
                timeout=45
            )

            persistence_elapsed = persistence.result(
                timeout=45
            )

        print(
            f"Transaction timeout: "
            f"{transaction_elapsed:.3f}s"
        )

        print(
            f"Persistence timeout: "
            f"{persistence_elapsed:.3f}s"
        )

        assert observer.execute(
            "SELECT pg_advisory_unlock(%s::bigint) AS released",
            (WAREHOUSE_KEY,),
        ).fetchone()["released"]

        with storage.transaction() as connection:

            assert connection.execute(
                "SELECT 1 AS value"
            ).fetchone()["value"] == 1

        run_id = uuid4()

        with RecoveryLockManager(storage).acquire(
            run_id,
            bind_connection=True,
        ):

            with persistence_guard(storage, run_id):

                with storage.transaction() as connection:

                    assert connection.execute(
                        "SELECT 1 AS value"
                    ).fetchone()["value"] == 1

        assert observer.execute(
            "SELECT pg_try_advisory_lock(%s::bigint) AS acquired",
            (WAREHOUSE_KEY,),
        ).fetchone()["acquired"]

        assert observer.execute(
            "SELECT pg_advisory_unlock(%s::bigint) AS released",
            (WAREHOUSE_KEY,),
        ).fetchone()["released"]

    finally:

        observer.close()


def test_transaction_preserves_previous_lock_timeout(storage):

    run_id = uuid4()

    with RecoveryLockManager(storage).acquire(
        run_id,
        bind_connection=True,
    ):

        from scrapers.storage.connection_context import (
            get_protected_connection,
        )

        connection = get_protected_connection().connection

        connection.execute(
            "SET lock_timeout = '7s'"
        )

        with storage.transaction() as active:

            assert active.execute(
                "SHOW lock_timeout"
            ).fetchone()["lock_timeout"] == "7s"

        assert connection.execute(
            "SHOW lock_timeout"
        ).fetchone()["lock_timeout"] == "7s"
