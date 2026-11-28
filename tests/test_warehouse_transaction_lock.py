import os
from uuid import uuid4

import pytest
import psycopg

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.concurrency import (
    WAREHOUSE_KEY,
)

from scrapers.storage.recovery_lock import (
    RecoveryLockManager,
)


pytestmark = pytest.mark.skipif(
    os.environ.get(
        "MATCHPOINT_RUN_CONCURRENCY_TESTS"
    ) != "1",
    reason="Requires isolated PostgreSQL database",
)


@pytest.fixture
def storage():

    settings = PostgresSettings(
        host="127.0.0.1",
        port=5432,
        database="matchpoint_ingestion_test",
        user="matchpoint",
        password=os.environ["POSTGRES_PASSWORD"],
    )

    instance = PostgresStorage(settings)

    with instance.transaction(
        read_only=True
    ) as connection:

        row = connection.execute("""
            SELECT
                current_database() AS database,
                current_setting(
                    'server_encoding'
                ) AS encoding,
                system_identifier::text AS cluster
            FROM pg_control_system()
        """).fetchone()

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
        """
        SELECT pg_try_advisory_lock(
            %s::bigint
        ) AS acquired
        """,
        (WAREHOUSE_KEY,),
    ).fetchone()["acquired"]


def release_exclusive(connection):

    assert connection.execute(
        """
        SELECT pg_advisory_unlock(
            %s::bigint
        ) AS released
        """,
        (WAREHOUSE_KEY,),
    ).fetchone()["released"]


def assert_available(connection):

    assert exclusive(connection)

    release_exclusive(connection)


def test_write_transaction_blocks_warehouse(
    storage, observer
):

    with storage.transaction():

        assert not exclusive(observer)

    assert_available(observer)


def test_read_only_does_not_block_warehouse(
    storage, observer
):

    with storage.transaction(read_only=True):

        assert_available(observer)


def test_parallel_write_transactions(
    storage, observer
):

    with storage.transaction():

        with storage.transaction():

            assert not exclusive(observer)

        assert not exclusive(observer)

    assert_available(observer)


def test_rollback_releases_guard(
    storage, observer
):

    with pytest.raises(
        RuntimeError,
        match="Intentional rollback",
    ):

        with storage.transaction():

            assert not exclusive(observer)

            raise RuntimeError(
                "Intentional rollback"
            )

    assert_available(observer)


def test_recovery_connection_guard(
    storage, observer
):

    manager = RecoveryLockManager(storage)

    with manager.acquire(
        uuid4(),
        bind_connection=True,
    ):

        with storage.transaction():

            assert not exclusive(observer)

        assert_available(observer)


def test_recovery_read_only_is_independent(
    storage, observer
):

    manager = RecoveryLockManager(storage)

    with manager.acquire(
        uuid4(),
        bind_connection=True,
    ):

        with storage.transaction(
            read_only=True
        ):

            assert_available(observer)


def test_recovery_rollback_releases_guard(
    storage, observer
):

    manager = RecoveryLockManager(storage)

    with manager.acquire(
        uuid4(),
        bind_connection=True,
    ):

        with pytest.raises(RuntimeError):

            with storage.transaction():

                assert not exclusive(observer)

                raise RuntimeError(
                    "Intentional rollback"
                )

        assert_available(observer)


def test_warehouse_allows_read_only(
    storage, observer
):

    assert exclusive(observer)

    try:

        with storage.transaction(
            read_only=True
        ) as connection:

            assert connection.execute(
                "SELECT 1 AS value"
            ).fetchone()["value"] == 1

    finally:

        release_exclusive(observer)


@pytest.mark.parametrize(
    "protected",
    [False, True],
)
def test_warehouse_blocks_write(
    storage, observer, monkeypatch, protected
):

    from contextlib import nullcontext

    original_connect = storage.connect

    def limited_connect(**kwargs):

        connection = original_connect(**kwargs)

        try:

            connection.execute(
                "SET statement_timeout = '300ms'"
            )

            connection.commit()

            return connection

        except BaseException:

            connection.close()
            raise

    monkeypatch.setattr(
        storage,
        "connect",
        limited_connect,
    )

    assert exclusive(observer)

    try:

        context = (
            RecoveryLockManager(storage).acquire(
                uuid4(),
                bind_connection=True,
            )
            if protected
            else nullcontext()
        )

        with context:

            with pytest.raises(
                psycopg.errors.QueryCanceled
            ):

                with storage.transaction():

                    pytest.fail(
                        "Write transaction bypassed warehouse lock"
                    )

    finally:

        release_exclusive(observer)

    assert_available(observer)


def test_connection_loss_releases_guard(
    storage, observer
):

    connection = storage.connect()

    try:

        connection.execute(
            """
            SELECT pg_advisory_xact_lock_shared(
                %s::bigint
            )
            """,
            (WAREHOUSE_KEY,),
        )

        assert not exclusive(observer)

    finally:

        connection.close()

    import time

    deadline = time.monotonic() + 5

    while time.monotonic() < deadline:

        if exclusive(observer):

            release_exclusive(observer)
            return

        time.sleep(0.05)

    pytest.fail(
        "Disconnected transaction retained lock"
    )


def test_read_only_transaction_enforced(
    storage,
):

    with storage.transaction(
        read_only=True
    ) as connection:

        row = connection.execute(
            """
            SELECT current_setting(
                'transaction_read_only'
            ) AS value
            """
        ).fetchone()

        assert row["value"] == "on"
