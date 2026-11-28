import os

from unittest.mock import Mock

import psycopg
import pytest

from scrapers.storage.concurrency import (
    ConcurrencyManager,
    WAREHOUSE_KEY,
)

from test_protected_warehouse import module


pytestmark = pytest.mark.skipif(
    os.environ.get(
        "MATCHPOINT_RUN_CONCURRENCY_TESTS"
    ) != "1",
    reason="Requires isolated PostgreSQL database",
)


@pytest.fixture
def connection_factory():

    def connect():

        connection = psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname="matchpoint_ingestion_test",
            user="matchpoint",
            password=os.environ["POSTGRES_PASSWORD"],
            autocommit=True,
            connect_timeout=5,
        )

        try:

            assert connection.execute(
                "SELECT current_database(), "
                "system_identifier::text "
                "FROM pg_control_system()"
            ).fetchone() == (
                "matchpoint_ingestion_test",
                "7711828057299574822",
            )

            return connection

        except BaseException:

            connection.close()
            raise

    return connect


def test_real_publication_gate_accepts_empty_database(
    connection_factory,
):

    manager = ConcurrencyManager(
        connection_factory,
        timeout=2,
    )

    stages = []

    def runner(stage, connection):

        with connection_factory() as observer:

            acquired = observer.execute(
                "SELECT pg_try_advisory_lock_shared(%s::bigint)",
                (WAREHOUSE_KEY,),
            ).fetchone()[0]

            assert not acquired

        stages.append(stage)

        return 0

    assert module.execute_protected(
        manager,
        runner,
        publication_gate=module.verify_publication_ready,
    ) == 0

    assert stages == ["seed", "run", "test"]

    with connection_factory() as observer:

        assert observer.execute(
            "SELECT pg_try_advisory_lock(%s::bigint)",
            (WAREHOUSE_KEY,),
        ).fetchone()[0]

        assert observer.execute(
            "SELECT pg_advisory_unlock(%s::bigint)",
            (WAREHOUSE_KEY,),
        ).fetchone()[0]


def test_real_warehouse_releases_lock_on_gate_failure(
    connection_factory,
):

    manager = ConcurrencyManager(
        connection_factory,
        timeout=2,
    )

    runner = Mock()

    def gate(connection):

        module.verify_publication_ready(connection)

        raise module.PublicationBlockedError(
            "Simulated publication refusal"
        )

    with pytest.raises(module.PublicationBlockedError):

        module.execute_protected(
            manager,
            runner,
            publication_gate=gate,
        )

    runner.assert_not_called()

    with connection_factory() as observer:

        assert observer.execute(
            "SELECT pg_try_advisory_lock(%s::bigint)",
            (WAREHOUSE_KEY,),
        ).fetchone()[0]

        assert observer.execute(
            "SELECT pg_advisory_unlock(%s::bigint)",
            (WAREHOUSE_KEY,),
        ).fetchone()[0]
