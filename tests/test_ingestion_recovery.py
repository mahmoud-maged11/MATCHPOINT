import os

from datetime import timedelta

import pytest

from scrapers.models import Opportunity

from scrapers.storage.collection_runs import (
    CollectionRunError,
)

from scrapers.storage.invalid_records import (
    InvalidRecordRepository,
)

from test_ingestion_atomicity import context


pytestmark = pytest.mark.skipif(
    os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1",
    reason="Requires isolated ingestion test database",
)


class LostAcknowledgement(ConnectionError):
    pass


def lose_acknowledgement(operation, *args, **kwargs):

    operation(*args, **kwargs)

    raise LostAcknowledgement(
        "Simulated lost acknowledgement after commit"
    )


def test_recover_committed_insert(context):

    repository = context["repository"]

    run_id = context["start_run"]()

    opportunity = context["base"]

    with pytest.raises(LostAcknowledgement):

        lose_acknowledgement(
            repository.ingest,
            opportunity,
            run_id,
        )

    committed = context["snapshot"]()

    assert len(committed["listings"]) == 1
    assert len(committed["history"]) == 1
    assert len(committed["observations"]) == 1

    recovered = repository.ingest(
        opportunity,
        run_id,
    )

    assert recovered.outcome == "duplicate"
    assert recovered.original_outcome == "inserted"
    assert recovered.content_version == 1

    assert recovered.source_listing_id == (
        committed["listings"][0]["source_listing_id"]
    )

    assert context["snapshot"]() == committed

    final = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=1,
    )

    assert final["records_inserted"] == 1
    assert final["records_received"] == 1


def test_recover_committed_update(context):

    initial = context["seed"]()

    repository = context["repository"]

    run_id = context["start_run"]()

    base = context["base"]

    updated = Opportunity.model_validate({
        **base.model_dump(mode="python"),
        "title": "Senior Data Engineer",
        "collected_at": (
            base.collected_at + timedelta(hours=1)
        ),
        "raw_payload": {"version": 2},
    })

    with pytest.raises(LostAcknowledgement):

        lose_acknowledgement(
            repository.ingest,
            updated,
            run_id,
        )

    committed = context["snapshot"]()

    assert len(committed["listings"]) == 1
    assert len(committed["history"]) == 2
    assert len(committed["observations"]) == 2

    recovered = repository.ingest(
        updated,
        run_id,
    )

    assert recovered.outcome == "duplicate"
    assert recovered.original_outcome == "updated"
    assert recovered.content_version == 2

    assert recovered.source_listing_id == (
        initial.source_listing_id
    )

    assert context["snapshot"]() == committed

    final = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=1,
    )

    assert final["records_updated"] == 1


def test_recover_committed_invalid_record(context):

    repository = InvalidRecordRepository(
        context["storage"]
    )

    run_id = context["start_run"]()

    arguments = {
        "run_id": run_id,
        "source_name": "wuzzuf",
        "failure_stage": "validation",
        "error_code": "MissingTitle",
        "error_message": "Required title is missing",
        "record_payload": {"title": None},
    }

    with pytest.raises(LostAcknowledgement):

        lose_acknowledgement(
            repository.record,
            **arguments,
        )

    committed = context["snapshot"]()

    assert len(committed["invalid"]) == 1

    recovered = repository.record(
        **arguments,
    )

    assert recovered.inserted is False

    assert recovered.invalid_record_id == (
        committed["invalid"][0]["invalid_record_id"]
    )

    assert recovered.rejection_hash == (
        committed["invalid"][0]["rejection_hash"]
    )

    assert context["snapshot"]() == committed

    final = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=1,
    )

    assert final["records_invalid"] == 1


def test_recover_committed_finalization(context):

    manager = context["manager"]

    run_id = context["start_run"]()

    result = context["repository"].ingest(
        context["base"],
        run_id,
    )

    assert result.outcome == "inserted"

    arguments = {
        "run_id": run_id,
        "status": "completed",
        "received": 1,
    }

    with pytest.raises(LostAcknowledgement):

        lose_acknowledgement(
            manager.finish_run,
            **arguments,
        )

    committed = context["snapshot"]()

    recovered = manager.get_run(run_id)

    assert recovered["status"] == "completed"
    assert recovered["finished_at"] is not None
    assert recovered["records_received"] == 1
    assert recovered["records_inserted"] == 1

    with pytest.raises(CollectionRunError):

        manager.finish_run(**arguments)

    assert manager.get_run(run_id) == recovered

    assert context["snapshot"]() == committed

    retry = context["repository"].ingest(
        context["base"],
        run_id,
    )

    assert retry.outcome == "duplicate"

    assert context["snapshot"]() == committed


def test_resume_interrupted_running_run(context):

    repository = context["repository"]
    manager = context["manager"]
    counter = context["counter"]

    run_id = context["start_run"]()

    base = context["base"]

    records = [
        Opportunity.model_validate({
            **base.model_dump(mode="python"),
            "title": f"Data Engineer Version {index}",
            "collected_at": (
                base.collected_at
                + timedelta(minutes=index)
            ),
            "raw_payload": {"version": index},
        })
        for index in range(5)
    ]

    # Each logical run accepts one observation per listing.
    # Use distinct runs for successive versions.

    first = repository.ingest(
        records[0],
        run_id,
    )

    assert first.outcome == "inserted"

    before = context["snapshot"]()

    # Simulate worker interruption before finalization.

    recovered_run = manager.get_run(run_id)

    assert recovered_run["status"] == "running"
    assert recovered_run["finished_at"] is None

    counters = counter.reconcile(
        run_id=run_id,
        received=2,
    )

    assert counters.processed == 1
    assert counters.unprocessed == 1

    # Recreate the repository as a restarted worker.

    from scrapers.storage.opportunities import (
        OpportunityRepository,
    )

    restarted = OpportunityRepository(
        context["storage"]
    )

    replay = restarted.ingest(
        records[0],
        run_id,
    )

    assert replay.outcome == "duplicate"
    assert context["snapshot"]() == before

    invalid = InvalidRecordRepository(
        context["storage"]
    )

    rejection = invalid.record(
        run_id=run_id,
        source_name="wuzzuf",
        failure_stage="validation",
        error_code="MissingTitle",
        error_message="Required title is missing",
        record_payload={"title": None},
    )

    assert rejection.inserted

    final = manager.finish_run(
        run_id=run_id,
        status="completed",
        received=2,
    )

    assert final["records_received"] == 2
    assert final["records_inserted"] == 1
    assert final["records_invalid"] == 1

    snapshot = context["snapshot"]()

    assert len(snapshot["listings"]) == 1
    assert len(snapshot["history"]) == 1
    assert len(snapshot["observations"]) == 1
    assert len(snapshot["invalid"]) == 1


def test_recover_finalized_partial_run(context):

    repository = context["repository"]
    manager = context["manager"]

    original_run = context["start_run"]()

    base = context["base"]

    initial = repository.ingest(
        base,
        original_run,
    )

    assert initial.outcome == "inserted"

    partial = manager.finish_run(
        run_id=original_run,
        status="partial",
        received=2,
        error_message="Simulated worker interruption",
    )

    assert partial["status"] == "partial"
    assert partial["records_received"] == 2
    assert partial["records_inserted"] == 1

    committed = context["snapshot"]()

    replay = repository.ingest(
        base,
        original_run,
    )

    assert replay.outcome == "duplicate"
    assert context["snapshot"]() == committed

    invalid = InvalidRecordRepository(
        context["storage"]
    )

    with pytest.raises(Exception) as error:

        invalid.record(
            run_id=original_run,
            source_name="wuzzuf",
            failure_stage="validation",
            error_code="MissingTitle",
            error_message="Required title is missing",
            record_payload={"title": None},
        )

    assert "run" in str(error.value).lower()

    assert context["snapshot"]() == committed

    recovery_run = context["start_run"]()

    assert recovery_run != original_run

    recovered = repository.ingest(
        base,
        recovery_run,
    )

    assert recovered.outcome == "unchanged"

    assert recovered.source_listing_id == (
        initial.source_listing_id
    )

    rejection = invalid.record(
        run_id=recovery_run,
        source_name="wuzzuf",
        failure_stage="validation",
        error_code="MissingTitle",
        error_message="Required title is missing",
        record_payload={"title": None},
    )

    assert rejection.inserted

    final = manager.finish_run(
        run_id=recovery_run,
        status="completed",
        received=2,
    )

    assert final["records_unchanged"] == 1
    assert final["records_invalid"] == 1

    assert manager.get_run(original_run) == partial

    snapshot = context["snapshot"]()

    assert len(snapshot["listings"]) == 1
    assert len(snapshot["history"]) == 1
    assert len(snapshot["observations"]) == 2
    assert len(snapshot["invalid"]) == 1


@pytest.mark.parametrize(
    "scenario,method_name",
    [
        ("insert", "_insert_history"),
        ("update", "_insert_history"),
        ("insert", "_insert_observation"),
    ],
)
def test_database_connection_failure(
    context,
    monkeypatch,
    scenario,
    method_name,
):

    from psycopg import OperationalError

    from scrapers.storage.opportunities import (
        OpportunityRepository,
    )

    storage = context["storage"]
    repository = context["repository"]
    manager = context["manager"]

    opportunity = context["base"]

    if scenario == "update":

        context["seed"]()

        opportunity = Opportunity.model_validate({
            **opportunity.model_dump(mode="python"),
            "title": "Senior Data Engineer",
            "collected_at": (
                opportunity.collected_at
                + timedelta(hours=1)
            ),
            "raw_payload": {"version": 2},
        })

    run_id = context["start_run"]()

    before = context["snapshot"]()

    original_method = getattr(
        repository,
        method_name,
    )

    original_connect = storage.connect

    connections = []
    terminated_pids = []

    def tracked_connect(*, read_only=False):

        conn = original_connect(
            read_only=read_only,
        )

        if not read_only:

            connections.append(conn)

        return conn

    def terminate_after_write(*args, **kwargs):

        result = original_method(
            *args,
            **kwargs,
        )

        assert len(connections) == 1

        victim = connections[0]

        assert victim.info.dbname == (
            "matchpoint_ingestion_test"
        )

        victim_pid = victim.info.backend_pid

        # Use an independent connection to terminate
        # only the active test transaction.

        with original_connect(
            read_only=False
        ) as control:

            target = control.execute(
                """
                SELECT pid
                FROM pg_stat_activity
                WHERE pid = %s
                  AND pid <> pg_backend_pid()
                  AND datname = current_database()
                  AND datname = 'matchpoint_ingestion_test'
                  AND usename = current_user
                  AND application_name = 'matchpoint_ingestion'
                """,
                (victim_pid,),
            ).fetchone()

            assert target is not None

            row = control.execute(
                """
                SELECT pg_terminate_backend(
                    %s,
                    5000
                ) AS terminated
                """,
                (victim_pid,),
            ).fetchone()

            assert row["terminated"] is True

        terminated_pids.append(victim_pid)

        # Force the client to detect the lost connection.

        victim.execute("SELECT 1")

        return result

    with monkeypatch.context() as patch:

        patch.setattr(
            storage,
            "connect",
            tracked_connect,
        )

        patch.setattr(
            repository,
            method_name,
            terminate_after_write,
        )

        with pytest.raises(OperationalError):

            repository.ingest(
                opportunity,
                run_id,
            )

    assert len(terminated_pids) == 1

    assert all(
        conn.closed
        for conn in connections
    )

    # Verify rollback using a fresh connection.

    assert context["snapshot"]() == before

    assert manager.get_run(
        run_id
    )["status"] == "running"

    counters = context["counter"].reconcile(
        run_id=run_id,
        received=1,
    )

    assert counters.processed == 0
    assert counters.unprocessed == 1

    # Retry using a new repository and connection.

    restarted = OpportunityRepository(storage)

    recovered = restarted.ingest(
        opportunity,
        run_id,
    )

    expected_outcome = (
        "updated"
        if scenario == "update"
        else "inserted"
    )

    expected_version = (
        2 if scenario == "update" else 1
    )

    assert recovered.outcome == expected_outcome

    assert recovered.content_version == (
        expected_version
    )

    after = context["snapshot"]()

    assert len(after["listings"]) == 1

    assert len(after["history"]) == (
        expected_version
    )

    assert len(after["observations"]) == (
        expected_version
    )

    assert after["invalid"] == before["invalid"]

    final = manager.finish_run(
        run_id=run_id,
        status="completed",
        received=1,
    )

    assert final["status"] == "completed"

    assert final[
        f"records_{expected_outcome}"
    ] == 1

    print(
        f"PASS: Backend {terminated_pids[0]} "
        f"terminated; rollback and retry verified"
    )
