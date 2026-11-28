import pytest

from scrapers.storage.connection_context import (
    get_protected_connection,
)

from scrapers.storage.orchestrator import (
    IngestionExecutionError,
)

from test_incremental_pipeline import (
    pipeline,
    make_scraper,
    execute,
)


def terminate_protected_backend(storage, run_id):

    protected = get_protected_connection()

    assert protected is not None
    assert protected.storage is storage
    assert protected.run_id == run_id

    pid = protected.connection.info.backend_pid

    assert isinstance(pid, int)
    assert pid > 0

    # Independent connection, never the protected session.
    with storage.connect() as conn:

        conn.autocommit = True

        identity = conn.execute("""
            SELECT
                current_database() AS database,
                current_user AS username,
                pg_backend_pid() AS pid
        """).fetchone()

        assert identity["database"] == (
            "matchpoint_ingestion_test"
        )

        assert identity["username"] == "matchpoint"
        assert identity["pid"] != pid

        target = conn.execute("""
            SELECT
                pid,
                datname,
                usename,
                application_name
            FROM pg_stat_activity
            WHERE pid = %s
        """, (pid,)).fetchone()

        assert target is not None

        assert target["datname"] == (
            "matchpoint_ingestion_test"
        )

        assert target["usename"] == "matchpoint"

        assert target["application_name"] == (
            "matchpoint_ingestion"
        )

        row = conn.execute("""
            SELECT pg_terminate_backend(
                %s,
                5000
            ) AS terminated
        """, (pid,)).fetchone()

        assert row["terminated"] is True


def persisted_counts(storage, run_id):

    assert get_protected_connection() is None

    with storage.transaction(
        read_only=True
    ) as conn:

        counts = []

        for table, column in (
            (
                "source_listings",
                "last_collection_run_id",
            ),
            (
                "source_listing_history",
                "collection_run_id",
            ),
            (
                "ingestion_observations",
                "collection_run_id",
            ),
        ):

            row = conn.execute(
                f"SELECT COUNT(*) AS n "
                f"FROM bronze.{table} "
                f"WHERE {column} = %s",
                (run_id,),
            ).fetchone()

            counts.append(row["n"])

        return tuple(counts)


def assert_recovered(pipeline, recovered):

    row = recovered.finalized_run

    assert row["status"] == "completed"

    assert row["records_received"] == 3
    assert row["records_inserted"] == 3

    for field in (
        "updated",
        "unchanged",
        "invalid",
        "stale",
        "conflicted",
    ):

        assert row[f"records_{field}"] == 0

    receipt = row["metadata"][
        "checkpoint_finalization"
    ]

    assert receipt["outcome"] == "advanced"

    checkpoint = pipeline["checkpoint"]()

    assert checkpoint is not None

    assert checkpoint[
        "last_successful_run_id"
    ] == pipeline["run_id"]

    assert persisted_counts(
        pipeline["orchestrator"].storage,
        pipeline["run_id"],
    ) == (3, 3, 3)


@pytest.mark.parametrize(
    "failure_point,expected_count",
    [
        ("before_commit", 0),
        ("after_commit", 2),
    ],
)
def test_real_backend_loss(
    pipeline,
    monkeypatch,
    failure_point,
    expected_count,
):

    orchestrator = pipeline["orchestrator"]
    storage = orchestrator.storage
    run_id = pipeline["run_id"]

    orchestrator.batch_size = 2

    repository = orchestrator.opportunities

    terminated = False

    if failure_point == "before_commit":

        original = repository._insert_observation

        def interrupt(*args, **kwargs):

            nonlocal terminated

            result = original(*args, **kwargs)

            if not terminated:

                terminated = True

                terminate_protected_backend(
                    storage,
                    run_id,
                )

                # Force detection inside the transaction.
                protected = get_protected_connection()

                protected.connection.execute(
                    "SELECT 1"
                )

            return result

        monkeypatch.setattr(
            repository,
            "_insert_observation",
            interrupt,
        )

    else:

        original = repository.ingest_many

        def interrupt(*args, **kwargs):

            nonlocal terminated

            result = original(*args, **kwargs)

            if not terminated:

                terminated = True

                terminate_protected_backend(
                    storage,
                    run_id,
                )

                protected = get_protected_connection()

                protected.connection.execute(
                    "SELECT 1"
                )

            return result

        monkeypatch.setattr(
            repository,
            "ingest_many",
            interrupt,
        )

    with pytest.raises(IngestionExecutionError):

        execute(
            pipeline,
            make_scraper(),
        )

    assert terminated

    assert get_protected_connection() is None

    assert persisted_counts(
        storage,
        run_id,
    ) == (expected_count,) * 3

    assert pipeline["checkpoint"]() is None

    snapshot = pipeline["store"].load(run_id)

    assert snapshot.accepted_count == 3

    # New orchestrator, connection and recovery lock.
    recovery = pipeline["new_orchestrator"]()

    recovery.batch_size = 100

    recovered = recovery.recover(
        run_id=run_id
    )

    assert_recovered(
        pipeline,
        recovered,
    )

    repeated = recovery.recover(
        run_id=run_id
    )

    assert repeated.already_finalized

    assert (
        repeated.finalized_run
        == recovered.finalized_run
    )


def test_backend_loss_after_finalization(
    pipeline,
    monkeypatch,
):

    orchestrator = pipeline["orchestrator"]
    storage = orchestrator.storage
    run_id = pipeline["run_id"]

    orchestrator.batch_size = 100

    original = orchestrator.runs.finish_run

    terminated = False

    def interrupt(*args, **kwargs):

        nonlocal terminated

        result = original(*args, **kwargs)

        if not terminated:

            terminated = True

            terminate_protected_backend(
                storage,
                run_id,
            )

            protected = get_protected_connection()

            protected.connection.execute(
                "SELECT 1"
            )

        return result

    monkeypatch.setattr(
        orchestrator.runs,
        "finish_run",
        interrupt,
    )

    with pytest.raises(IngestionExecutionError):

        execute(
            pipeline,
            make_scraper(),
        )

    assert terminated

    assert get_protected_connection() is None

    recovery = pipeline["new_orchestrator"]()

    recovered = recovery.recover(
        run_id=run_id
    )

    assert recovered.already_finalized

    assert_recovered(
        pipeline,
        recovered,
    )
