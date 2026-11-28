import os

from uuid import uuid4

import psycopg
import pytest

from psycopg.rows import dict_row
from psycopg.pq import TransactionStatus

from scrapers.storage.checkpoints import (
    CheckpointAdvance,
    CheckpointError,
    CheckpointRepository,
)


pytestmark = pytest.mark.skipif(
    os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1",
    reason="Requires isolated PostgreSQL database",
)


@pytest.fixture
def connection():

    conn = psycopg.connect(
        host="127.0.0.1",
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname="matchpoint_ingestion_test",
        row_factory=dict_row,
        autocommit=True,
        connect_timeout=10,
    )

    try:

        assert conn.execute(
            "SELECT current_database() AS db"
        ).fetchone()["db"] == "matchpoint_ingestion_test"

        yield conn

    finally:

        conn.close()


def advance(connection):

    return CheckpointRepository._advance(
        connection,
        run_id=uuid4(),
        advance=CheckpointAdvance(
            checkpoint_type="timestamp",
            checkpoint_value={
                "timestamp": "2026-01-01T00:00:00+00:00"
            },
            expected_previous_run_id=None,
        ),
    )


def test_idle_connection_rejected(connection):

    assert (
        connection.info.transaction_status
        == TransactionStatus.IDLE
    )

    with pytest.raises(
        CheckpointError,
        match="An active transaction is required",
    ):
        advance(connection)


def test_explicit_transaction_accepted(connection):

    with connection.transaction():

        assert connection.autocommit is True

        assert (
            connection.info.transaction_status
            == TransactionStatus.INTRANS
        )

        # The guard must allow the call to reach
        # the actual run validation.

        with pytest.raises(
            CheckpointError,
            match="Collection run not found",
        ):
            advance(connection)


def test_failed_transaction_rejected(connection):

    with connection.transaction():

        with pytest.raises(psycopg.errors.DivisionByZero):

            connection.execute("SELECT 1 / 0")

        assert (
            connection.info.transaction_status
            == TransactionStatus.INERROR
        )

        with pytest.raises(
            CheckpointError,
            match="An active transaction is required",
        ):
            advance(connection)


def test_closed_connection_rejected(connection):

    connection.close()

    with pytest.raises(
        CheckpointError,
        match="An active transaction is required",
    ):
        advance(connection)


def test_non_autocommit_idle_rejected(connection):

    connection.autocommit = False

    assert (
        connection.info.transaction_status
        == TransactionStatus.IDLE
    )

    with pytest.raises(
        CheckpointError,
        match="An active transaction is required",
    ):
        advance(connection)


def test_non_autocommit_active_accepted(connection):

    connection.autocommit = False

    try:

        connection.execute("SELECT 1")

        assert (
            connection.info.transaction_status
            == TransactionStatus.INTRANS
        )

        with pytest.raises(
            CheckpointError,
            match="Collection run not found",
        ):
            advance(connection)

    finally:

        connection.rollback()
