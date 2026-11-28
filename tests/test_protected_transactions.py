import os

from uuid import uuid4

import psycopg
import pytest

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.recovery_lock import (
    RecoveryLockManager,
    RecoveryAlreadyRunningError,
)

from scrapers.storage.connection_context import (
    get_protected_connection,
    ProtectedConnectionError,
)


@pytest.fixture
def storage():

    if os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests disabled")

    storage = PostgresStorage(
        PostgresSettings.from_config(
            host="127.0.0.1",
            database="matchpoint_ingestion_test",
        )
    )

    with storage.transaction(read_only=True) as conn:

        row = conn.execute(
            "SELECT current_database() AS db"
        ).fetchone()

        assert row["db"] == "matchpoint_ingestion_test"

    return storage


@pytest.fixture
def manager(storage):

    return RecoveryLockManager(storage)


def terminate_connection(storage, pid):

    with storage.connect() as conn:

        row = conn.execute(
            """
            SELECT pg_terminate_backend(pid) AS terminated
            FROM pg_stat_activity
            WHERE pid = %s
              AND datname = 'matchpoint_ingestion_test'
              AND usename = current_user
              AND application_name = 'matchpoint_ingestion'
              AND pid <> pg_backend_pid()
            """,
            (pid,),
        ).fetchone()

        assert row is not None
        assert row["terminated"]


def test_protected_context_identity(storage, manager):

    run_id = uuid4()

    assert get_protected_connection() is None

    with manager.acquire(
        run_id,
        bind_connection=True,
    ):

        protected = get_protected_connection()

        assert protected.storage is storage
        assert protected.run_id == run_id

    assert get_protected_connection() is None


def test_transactions_share_lock_connection(
    storage,
    manager,
):
    with manager.acquire(
        uuid4(),
        bind_connection=True,
    ):

        protected = get_protected_connection()

        with storage.transaction() as conn:

            assert conn is protected.connection

            first = conn.execute(
                "SELECT pg_backend_pid() AS pid"
            ).fetchone()

        with storage.transaction() as conn:

            assert conn is protected.connection

            second = conn.execute(
                "SELECT pg_backend_pid() AS pid"
            ).fetchone()

        assert first["pid"] == second["pid"]


def test_read_only_transaction_isolation(
    storage,
    manager,
):
    with manager.acquire(
        uuid4(),
        bind_connection=True,
    ):

        with storage.transaction(read_only=True) as conn:

            row = conn.execute(
                """
                SELECT current_setting(
                    'transaction_read_only'
                ) AS mode
                """
            ).fetchone()

            assert row["mode"] == "on"

        with storage.transaction() as conn:

            row = conn.execute(
                """
                SELECT current_setting(
                    'transaction_read_only'
                ) AS mode
                """
            ).fetchone()

            assert row["mode"] == "off"


def test_independent_storage_blocked(
    storage,
    manager,
):
    another = PostgresStorage(storage.settings)

    with manager.acquire(
        uuid4(),
        bind_connection=True,
    ):

        with pytest.raises(ProtectedConnectionError):

            with another.transaction():
                pytest.fail("Independent connection accepted")


def test_nested_protected_context_rejected(
    storage,
    manager,
):
    with manager.acquire(
        uuid4(),
        bind_connection=True,
    ):

        original = get_protected_connection()

        with pytest.raises(ProtectedConnectionError):

            with manager.acquire(
                uuid4(),
                bind_connection=True,
            ):
                pytest.fail("Nested context accepted")

        assert get_protected_connection() is original

    assert get_protected_connection() is None


def test_context_cleared_after_exception(manager):

    with pytest.raises(ValueError):

        with manager.acquire(
            uuid4(),
            bind_connection=True,
        ):
            raise ValueError("Simulated failure")

    assert get_protected_connection() is None


def test_context_cleared_after_interrupt(manager):

    with pytest.raises(KeyboardInterrupt):

        with manager.acquire(
            uuid4(),
            bind_connection=True,
        ):
            raise KeyboardInterrupt()

    assert get_protected_connection() is None


def test_transaction_rollback_preserves_lock(
    storage,
    manager,
):
    run_id = uuid4()

    with manager.acquire(
        run_id,
        bind_connection=True,
    ):

        with storage.transaction() as conn:

            conn.execute(
                """
                CREATE TEMP TABLE rollback_probe (
                    value INTEGER
                )
                """
            )

        with pytest.raises(RuntimeError):

            with storage.transaction() as conn:

                conn.execute(
                    "INSERT INTO rollback_probe VALUES (1)"
                )

                raise RuntimeError("Rollback required")

        with storage.transaction() as conn:

            row = conn.execute(
                "SELECT COUNT(*) AS count FROM rollback_probe"
            ).fetchone()

            assert row["count"] == 0

        with pytest.raises(RecoveryAlreadyRunningError):

            with manager.acquire(run_id):
                pytest.fail("Lock released after rollback")


def test_lost_connection_prevents_fallback(
    storage,
    manager,
):
    run_id = uuid4()

    with manager.acquire(
        run_id,
        bind_connection=True,
    ):

        with storage.transaction() as conn:

            row = conn.execute(
                "SELECT pg_backend_pid() AS pid"
            ).fetchone()

            original_pid = row["pid"]

        terminate_connection(
            storage,
            original_pid,
        )

        with pytest.raises(
            (psycopg.Error, ProtectedConnectionError)
        ):

            with storage.transaction() as conn:
                conn.execute("SELECT 1")

        with pytest.raises(ProtectedConnectionError):

            with storage.transaction():
                pytest.fail("Fallback connection opened")

    assert get_protected_connection() is None

    with manager.acquire(
        run_id,
        bind_connection=True,
    ):

        with storage.transaction() as conn:

            row = conn.execute(
                "SELECT pg_backend_pid() AS pid"
            ).fetchone()

            assert row["pid"] != original_pid


def test_connection_loss_rolls_back_uncommitted_write(
    storage,
    manager,
):
    run_id = uuid4()

    table = f"protected_probe_{uuid4().hex}"

    with storage.transaction() as conn:

        conn.execute(
            f"""
            CREATE TABLE public.{table} (
                value INTEGER NOT NULL
            )
            """
        )

    try:

        with manager.acquire(
            run_id,
            bind_connection=True,
        ):

            with pytest.raises(
                (psycopg.Error, ProtectedConnectionError)
            ):

                with storage.transaction() as conn:

                    conn.execute(
                        f"INSERT INTO public.{table} VALUES (1)"
                    )

                    row = conn.execute(
                        "SELECT pg_backend_pid() AS pid"
                    ).fetchone()

                    terminate_connection(
                        storage,
                        row["pid"],
                    )

                    conn.execute("SELECT 1")

        assert get_protected_connection() is None

        with manager.acquire(
            run_id,
            bind_connection=True,
        ):

            with storage.transaction() as conn:

                row = conn.execute(
                    f"SELECT COUNT(*) AS count FROM public.{table}"
                ).fetchone()

                assert row["count"] == 0

                conn.execute(
                    f"INSERT INTO public.{table} VALUES (2)"
                )

        with storage.transaction() as conn:

            rows = conn.execute(
                f"SELECT value FROM public.{table}"
            ).fetchall()

            assert rows == [{"value": 2}]

    finally:

        with storage.transaction() as conn:

            conn.execute(
                f"DROP TABLE IF EXISTS public.{table}"
            )
