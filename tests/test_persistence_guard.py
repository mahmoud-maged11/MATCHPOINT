import os
import time

from uuid import uuid4

import pytest

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

from scrapers.storage.connection_context import (
    ProtectedConnectionError,
    ProtectedConnectionLostError,
)

from scrapers.storage.concurrency import (
    WAREHOUSE_KEY,
)


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
            "current_setting('server_encoding') AS encoding, "
            "system_identifier::text AS cluster "
            "FROM pg_control_system()"
        ).fetchone()

        assert row == {
            "database": "matchpoint_ingestion_test",
            "encoding": "UTF8",
            "cluster": "7711828057299574822",
        }

    return instance


@pytest.fixture
def observer(storage):

    connection = storage.connect()
    connection.autocommit = True

    try:
        yield connection

    finally:
        connection.close()


def exclusive(connection):

    return connection.execute(
        "SELECT pg_try_advisory_lock(%s::bigint) AS acquired",
        (WAREHOUSE_KEY,),
    ).fetchone()["acquired"]


def available(connection):

    assert exclusive(connection)

    assert connection.execute(
        "SELECT pg_advisory_unlock(%s::bigint) AS released",
        (WAREHOUSE_KEY,),
    ).fetchone()["released"]


def test_guard_requires_protected_connection(storage):

    with pytest.raises(ProtectedConnectionError):

        with persistence_guard(storage, uuid4()):
            pass


def test_guard_blocks_warehouse(storage, observer):

    run_id = uuid4()

    with RecoveryLockManager(storage).acquire(
        run_id, bind_connection=True
    ):

        with persistence_guard(storage, run_id):

            assert not exclusive(observer)

        available(observer)


def test_guard_spans_multiple_transactions(
    storage, observer
):

    run_id = uuid4()

    with RecoveryLockManager(storage).acquire(
        run_id, bind_connection=True
    ):

        with persistence_guard(storage, run_id):

            for _ in range(5):

                with storage.transaction() as connection:

                    connection.execute("SELECT 1")

                    assert not exclusive(observer)

                assert not exclusive(observer)

        available(observer)


def test_guard_survives_transaction_rollback(
    storage, observer
):

    run_id = uuid4()

    with RecoveryLockManager(storage).acquire(
        run_id, bind_connection=True
    ):

        with persistence_guard(storage, run_id):

            with pytest.raises(RuntimeError):

                with storage.transaction():

                    raise RuntimeError("Intentional rollback")

            assert not exclusive(observer)

        available(observer)


def test_guard_exception_cleanup(storage, observer):

    run_id = uuid4()

    with RecoveryLockManager(storage).acquire(
        run_id, bind_connection=True
    ):

        with pytest.raises(
            RuntimeError, match="Intentional failure"
        ):

            with persistence_guard(storage, run_id):

                raise RuntimeError("Intentional failure")

        available(observer)


def test_wrong_run_id_rejected(storage, observer):

    with RecoveryLockManager(storage).acquire(
        uuid4(), bind_connection=True
    ):

        with pytest.raises(ProtectedConnectionError):

            with persistence_guard(storage, uuid4()):
                pass

        available(observer)


def test_wrong_storage_rejected(storage, observer):

    run_id = uuid4()

    other = PostgresStorage(storage.settings)

    with RecoveryLockManager(storage).acquire(
        run_id, bind_connection=True
    ):

        with pytest.raises(ProtectedConnectionError):

            with persistence_guard(other, run_id):
                pass

        available(observer)


def test_scraping_does_not_hold_warehouse_lock(
    storage, observer
):

    run_id = uuid4()

    with RecoveryLockManager(storage).acquire(
        run_id, bind_connection=True
    ):

        available(observer)

        with persistence_guard(storage, run_id):

            assert not exclusive(observer)

        available(observer)


def test_connection_loss_detected(storage, observer):

    run_id = uuid4()

    with RecoveryLockManager(storage).acquire(
        run_id, bind_connection=True
    ):

        with pytest.raises(ProtectedConnectionLostError):

            with persistence_guard(
                storage, run_id
            ) as connection:

                assert not exclusive(observer)

                connection.close()

    deadline = time.monotonic() + 5

    while time.monotonic() < deadline:

        if exclusive(observer):

            observer.execute(
                "SELECT pg_advisory_unlock(%s::bigint)",
                (WAREHOUSE_KEY,),
            )

            return

        time.sleep(0.05)

    pytest.fail("Guard retained after disconnect")


def test_nested_guard_reference_count(storage, observer):

    run_id = uuid4()

    with RecoveryLockManager(storage).acquire(
        run_id, bind_connection=True
    ):

        with persistence_guard(storage, run_id):

            with persistence_guard(storage, run_id):

                assert not exclusive(observer)

            assert not exclusive(observer)

        available(observer)
