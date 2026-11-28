import os

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from scrapers.models import Opportunity

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.collection_runs import (
    CollectionRunManager,
)

from scrapers.storage.checkpoints import (
    CheckpointAdvance,
    CheckpointRepository,
    CheckpointError,
    CheckpointConflictError,
)

from scrapers.storage.invalid_records import (
    InvalidRecordRepository,
)

from scrapers.storage.opportunities import (
    OpportunityRepository,
)


pytestmark = pytest.mark.skipif(
    os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1",
    reason="Requires isolated ingestion test database",
)


@pytest.fixture
def context():

    storage = PostgresStorage(
        PostgresSettings.from_config(
            host="127.0.0.1",
            database="matchpoint_ingestion_test",
        )
    )

    assert storage.health_check()["database"] == (
        "matchpoint_ingestion_test"
    )

    manager = CollectionRunManager(storage)
    repository = CheckpointRepository(storage)

    scope = f"checkpoint_test_{uuid4().hex}"

    run_ids = []
    scopes = set()

    def start(source="egyincs", suffix="default"):

        current_scope = f"{scope}_{suffix}"

        run_id = manager.start_run(
            source_name=source,
            collection_mode="api",
            collection_scope=current_scope,
        )

        run_ids.append(run_id)
        scopes.add((source, current_scope))

        return run_id

    def get(source="egyincs", suffix="default"):

        return repository.get_checkpoint(
            source_name=source,
            collection_scope=f"{scope}_{suffix}",
        )

    def finish(run_id, checkpoint=None, received=0):

        return manager.finish_run(
            run_id=run_id,
            status="completed",
            received=received,
            checkpoint=checkpoint,
        )

    try:

        yield {
            "storage": storage,
            "manager": manager,
            "repository": repository,
            "start": start,
            "get": get,
            "finish": finish,
        }

    finally:

        with storage.transaction() as conn:

            for source, current_scope in scopes:

                conn.execute(
                    """
                    DELETE FROM bronze.source_checkpoints
                    WHERE source_name = %s
                      AND collection_scope = %s
                    """,
                    (source, current_scope),
                )

            for run_id in run_ids:

                for table in (
                    "invalid_records",
                    "ingestion_observations",
                    "source_listing_history",
                ):

                    from psycopg import sql

                    conn.execute(
                        sql.SQL(
                            "DELETE FROM bronze.{} "
                            "WHERE collection_run_id = %s"
                        ).format(sql.Identifier(table)),
                        (run_id,),
                    )

            for run_id in run_ids:

                conn.execute(
                    """
                    DELETE FROM bronze.source_listings
                    WHERE last_collection_run_id = %s
                    """,
                    (run_id,),
                )

            for run_id in run_ids:

                conn.execute(
                    """
                    DELETE FROM bronze.collection_runs
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )


def advance(value, previous=None):

    return CheckpointAdvance(
        checkpoint_type="numeric_id",
        checkpoint_value={"id": value},
        expected_previous_run_id=previous,
    )


def test_initial_checkpoint(context):

    run_id = context["start"]()

    assert context["get"]() is None

    result = context["finish"](
        run_id,
        advance(100),
    )

    checkpoint = context["get"]()

    assert result["status"] == "completed"
    assert checkpoint["checkpoint_value"] == {"id": 100}
    assert checkpoint["last_successful_run_id"] == run_id


def test_checkpoint_update(context):

    first = context["start"]()

    context["finish"](first, advance(100))

    before = context["get"]()

    second = context["start"]()

    context["finish"](
        second,
        advance(200, first),
    )

    after = context["get"]()

    assert after["checkpoint_value"] == {"id": 200}
    assert after["last_successful_run_id"] == second
    assert after["checkpoint_id"] == before["checkpoint_id"]
    assert after["created_at"] == before["created_at"]
    assert after["updated_at"] >= before["updated_at"]


@pytest.mark.parametrize(
    "source,suffix",
    [
        ("egyincs", "jobs"),
        ("egyincs", "lp_course"),
        ("wuzzuf", "jobs"),
    ],
)
def test_source_scope_isolation(
    context,
    source,
    suffix,
):

    first = context["start"](
        "egyincs",
        "baseline",
    )

    context["finish"](first, advance(100))

    before = context["get"](
        "egyincs",
        "baseline",
    )

    second = context["start"](source, suffix)

    context["finish"](second, advance(500))

    assert context["get"](
        source,
        suffix,
    )["checkpoint_value"] == {"id": 500}

    assert context["get"](
        "egyincs",
        "baseline",
    ) == before


def test_backward_checkpoint_rejected(context):

    first = context["start"]()

    context["finish"](first, advance(100))

    before = context["get"]()

    second = context["start"]()

    run_before = context["manager"].get_run(second)

    with pytest.raises(CheckpointConflictError):

        context["finish"](
            second,
            advance(50, first),
        )

    assert context["get"]() == before

    assert context["manager"].get_run(
        second
    ) == run_before


def test_stale_expectation_rejected(context):

    first = context["start"]()

    context["finish"](first, advance(100))

    second = context["start"]()

    context["finish"](
        second,
        advance(200, first),
    )

    before = context["get"]()

    third = context["start"]()

    with pytest.raises(CheckpointConflictError):

        context["finish"](
            third,
            advance(300, first),
        )

    assert context["get"]() == before

    assert context["manager"].get_run(
        third
    )["status"] == "running"


def test_missing_expected_checkpoint(context):

    run_id = context["start"]()

    with pytest.raises(CheckpointConflictError):

        context["finish"](
            run_id,
            advance(100, uuid4()),
        )

    assert context["get"]() is None

    assert context["manager"].get_run(
        run_id
    )["status"] == "running"


def test_older_run_rejected(context):

    older = context["start"]()
    newer = context["start"]()

    context["finish"](newer, advance(100))

    before = context["get"]()

    with pytest.raises(CheckpointConflictError):

        context["finish"](
            older,
            advance(200, newer),
        )

    assert context["get"]() == before

    assert context["manager"].get_run(
        older
    )["status"] == "running"


def test_checkpoint_type_change_rejected(context):

    first = context["start"]()

    context["finish"](first, advance(100))

    before = context["get"]()

    second = context["start"]()

    checkpoint = CheckpointAdvance(
        checkpoint_type="cursor",
        checkpoint_value={"cursor": "next"},
        expected_previous_run_id=first,
    )

    with pytest.raises(CheckpointConflictError):

        context["finish"](second, checkpoint)

    assert context["get"]() == before

    assert context["manager"].get_run(
        second
    )["status"] == "running"


@pytest.mark.parametrize(
    "status",
    ["partial", "failed", "aborted"],
)
def test_unsuccessful_run_cannot_advance(
    context,
    status,
):

    run_id = context["start"]()

    before = context["manager"].get_run(run_id)

    with pytest.raises(
        ValueError,
        match="Only completed runs",
    ):

        context["manager"].finish_run(
            run_id=run_id,
            status=status,
            received=0,
            error_message="Simulated failure",
            checkpoint=advance(100),
        )

    assert context["get"]() is None

    assert context["manager"].get_run(
        run_id
    ) == before


def test_invalid_record_blocks_advancement(context):

    run_id = context["start"]()

    repository = InvalidRecordRepository(
        context["storage"]
    )

    rejection = repository.record(
        run_id=run_id,
        source_name="egyincs",
        failure_stage="validation",
        error_code="MissingTitle",
        error_message="Missing title",
        record_payload={"title": None},
    )

    assert rejection.inserted

    before = context["manager"].get_run(run_id)

    with pytest.raises(CheckpointError):

        context["finish"](
            run_id,
            advance(100),
            received=1,
        )

    assert context["get"]() is None

    assert context["manager"].get_run(
        run_id
    ) == before

    final = context["finish"](
        run_id,
        received=1,
    )

    assert final["records_invalid"] == 1
    assert context["get"]() is None


def test_conflict_blocks_advancement(context):

    run_id = context["start"]()

    identifier = str(uuid4().int)

    opportunity = Opportunity(
        source_name="egyincs",
        source_opportunity_id=identifier,
        source_url=(
            f"https://egyincs.com/?p={identifier}"
        ),
        title="Data Engineer",
        opportunity_type="job",
        raw_payload={"id": identifier},
    )

    repository = OpportunityRepository(
        context["storage"]
    )

    inserted = repository.ingest(
        opportunity,
        run_id,
    )

    assert inserted.outcome == "inserted"

    changed = Opportunity.model_validate({
        **opportunity.model_dump(mode="python"),
        "title": "Senior Data Engineer",
    })

    conflict = repository.ingest(
        changed,
        run_id,
    )

    assert conflict.outcome == "conflicted"

    before = context["manager"].get_run(run_id)

    with pytest.raises(CheckpointError):

        context["finish"](
            run_id,
            advance(100),
            received=2,
        )

    assert context["get"]() is None

    assert context["manager"].get_run(
        run_id
    ) == before

    final = context["finish"](
        run_id,
        received=2,
    )

    assert final["records_inserted"] == 1
    assert final["records_conflicted"] == 1


def test_unprocessed_records_block_advancement(context):

    run_id = context["start"]()

    with pytest.raises(ValueError):

        context["finish"](
            run_id,
            advance(100),
            received=1,
        )

    assert context["get"]() is None

    assert context["manager"].get_run(
        run_id
    )["status"] == "running"


def test_completed_without_checkpoint(context):

    first = context["start"]()

    context["finish"](first, advance(100))

    before = context["get"]()

    second = context["start"]()

    context["finish"](second)

    assert context["get"]() == before


def test_failure_after_checkpoint_write(
    context,
    monkeypatch,
):

    run_id = context["start"]()

    before = context["manager"].get_run(run_id)

    original = CheckpointRepository._advance

    def fail_after_write(*args, **kwargs):

        original(*args, **kwargs)

        raise RuntimeError(
            "Simulated failure after checkpoint write"
        )

    with monkeypatch.context() as patch:

        patch.setattr(
            CheckpointRepository,
            "_advance",
            staticmethod(fail_after_write),
        )

        with pytest.raises(
            RuntimeError,
            match="Simulated failure",
        ):

            context["finish"](
                run_id,
                advance(100),
            )

    assert context["get"]() is None

    assert context["manager"].get_run(
        run_id
    ) == before

    context["finish"](
        run_id,
        advance(100),
    )

    assert context["get"]()[
        "last_successful_run_id"
    ] == run_id


@pytest.mark.parametrize(
    "existing_checkpoint",
    [False, True],
)
def test_concurrent_checkpoint_advancement(
    context,
    monkeypatch,
    existing_checkpoint,
):

    storage = context["storage"]

    previous = None

    if existing_checkpoint:

        previous = context["start"]()

        context["finish"](
            previous,
            advance(100),
        )

    first = context["start"]()
    second = context["start"]()

    barrier = Barrier(2)

    original_connect = storage.connect

    def bounded_connect(*, read_only=False):

        conn = original_connect(
            read_only=read_only,
        )

        try:

            conn.execute(
                "SET LOCAL lock_timeout = '5s'"
            )

            conn.execute(
                "SET LOCAL statement_timeout = '10s'"
            )

            return conn

        except BaseException:

            conn.close()
            raise

    def worker(run_id, value):

        barrier.wait(timeout=10)

        try:

            context["finish"](
                run_id,
                advance(value, previous),
            )

            return ("completed", run_id, value)

        except CheckpointConflictError:

            return ("conflict", run_id, value)

    with monkeypatch.context() as patch:

        patch.setattr(
            storage,
            "connect",
            bounded_connect,
        )

        with ThreadPoolExecutor(
            max_workers=2
        ) as executor:

            futures = [
                executor.submit(worker, first, 200),
                executor.submit(worker, second, 300),
            ]

            results = [
                future.result(timeout=30)
                for future in futures
            ]

    assert sorted(
        result[0]
        for result in results
    ) == ["completed", "conflict"]

    winner = next(
        result
        for result in results
        if result[0] == "completed"
    )

    loser = next(
        result
        for result in results
        if result[0] == "conflict"
    )

    checkpoint = context["get"]()

    assert checkpoint["last_successful_run_id"] == winner[1]

    assert checkpoint["checkpoint_value"] == {
        "id": winner[2]
    }

    assert context["manager"].get_run(
        winner[1]
    )["status"] == "completed"

    assert context["manager"].get_run(
        loser[1]
    )["status"] == "running"


# DURABLE CHECKPOINT RECEIPT TESTS

def expected_receipt(
    value,
    previous=None,
    outcome="advanced",
):

    return {
        "version": 1,
        "outcome": outcome,
        "checkpoint_type": "numeric_id",
        "checkpoint_value": {"id": value},
        "expected_previous_run_id": (
            str(previous)
            if previous is not None
            else None
        ),
    }


def test_durable_receipt_saved(context):

    run_id = context["start"]()

    result = context["finish"](
        run_id,
        advance(100),
    )

    receipt = expected_receipt(100)

    assert result["metadata"][
        "checkpoint_finalization"
    ] == receipt

    persisted = context["manager"].get_run(run_id)

    assert persisted["metadata"][
        "checkpoint_finalization"
    ] == receipt

    assert context["get"]()[
        "last_successful_run_id"
    ] == run_id


def test_normal_run_has_no_receipt(context):

    run_id = context["start"]()

    result = context["finish"](run_id)

    assert "checkpoint_finalization" not in (
        result["metadata"]
    )

    assert context["get"]() is None


def test_previous_receipt_preserved(context):

    first = context["start"]()

    context["finish"](first, advance(100))

    second = context["start"]()

    context["finish"](
        second,
        advance(200, first),
    )

    assert context["manager"].get_run(
        first
    )["metadata"]["checkpoint_finalization"] == (
        expected_receipt(100)
    )

    assert context["manager"].get_run(
        second
    )["metadata"]["checkpoint_finalization"] == (
        expected_receipt(200, first)
    )

    assert context["get"]()[
        "checkpoint_value"
    ] == {"id": 200}


def test_invalid_record_skips_checkpoint(context):

    first = context["start"]()

    context["finish"](first, advance(100))

    before = context["get"]()

    run_id = context["start"]()

    repository = InvalidRecordRepository(
        context["storage"]
    )

    rejection = repository.record(
        run_id=run_id,
        source_name="egyincs",
        failure_stage="validation",
        error_code="MissingTitle",
        error_message="Missing title",
        record_payload={"title": None},
    )

    assert rejection.inserted

    result = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=1,
        checkpoint=advance(200, first),
        skip_unsafe_checkpoint=True,
    )

    assert result["records_invalid"] == 1

    assert result["metadata"][
        "checkpoint_finalization"
    ] == expected_receipt(
        200,
        first,
        "skipped_unsafe_counters",
    )

    assert context["get"]() == before


def test_conflicted_record_skips_checkpoint(context):

    run_id = context["start"]()

    identifier = str(uuid4().int)

    opportunity = Opportunity(
        source_name="egyincs",
        source_opportunity_id=identifier,
        source_url=f"https://egyincs.com/?p={identifier}",
        title="Data Engineer",
        opportunity_type="job",
        raw_payload={"id": identifier},
    )

    repository = OpportunityRepository(
        context["storage"]
    )

    assert repository.ingest(
        opportunity,
        run_id,
    ).outcome == "inserted"

    changed = Opportunity.model_validate({
        **opportunity.model_dump(mode="python"),
        "title": "Senior Data Engineer",
    })

    assert repository.ingest(
        changed,
        run_id,
    ).outcome == "conflicted"

    result = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=2,
        checkpoint=advance(100),
        skip_unsafe_checkpoint=True,
    )

    assert result["records_conflicted"] == 1

    assert result["metadata"][
        "checkpoint_finalization"
    ] == expected_receipt(
        100,
        outcome="skipped_unsafe_counters",
    )

    assert context["get"]() is None


@pytest.mark.parametrize("skip_unsafe", [False, True])
def test_stale_record_checkpoint_guard(
    context,
    skip_unsafe,
):

    from datetime import timedelta

    first = context["start"]()

    identifier = str(uuid4().int)

    opportunity = Opportunity(
        source_name="egyincs",
        source_opportunity_id=identifier,
        source_url=f"https://egyincs.com/?p={identifier}",
        title="Current Data Engineer",
        opportunity_type="job",
        raw_payload={"id": identifier},
    )

    repository = OpportunityRepository(
        context["storage"]
    )

    assert repository.ingest(
        opportunity,
        first,
    ).outcome == "inserted"

    context["finish"](
        first,
        advance(100),
        received=1,
    )

    before = context["get"]()

    second = context["start"]()

    stale = Opportunity.model_validate({
        **opportunity.model_dump(mode="python"),
        "title": "Older Data Engineer",
        "collected_at": (
            opportunity.collected_at
            - timedelta(hours=1)
        ),
    })

    assert repository.ingest(
        stale,
        second,
    ).outcome == "stale"

    arguments = {
        "run_id": second,
        "status": "completed",
        "received": 1,
        "checkpoint": advance(200, first),
        "skip_unsafe_checkpoint": skip_unsafe,
    }

    if skip_unsafe:

        result = context["manager"].finish_run(
            **arguments
        )

        assert result["records_stale"] == 1

        assert result["metadata"][
            "checkpoint_finalization"
        ] == expected_receipt(
            200,
            first,
            "skipped_unsafe_counters",
        )

    else:

        run_before = context["manager"].get_run(second)

        with pytest.raises(CheckpointError):

            context["manager"].finish_run(
                **arguments
            )

        assert context["manager"].get_run(
            second
        ) == run_before

    assert context["get"]() == before


def test_receipt_recovery_after_ambiguous_commit(
    context,
    monkeypatch,
):

    import psycopg

    from scrapers.storage.run_recovery import RunRecovery
    from scrapers.storage.retry_policy import RetryPolicy

    manager = context["manager"]

    recovery = RunRecovery(
        manager,
        RetryPolicy(),
    )

    run_id = context["start"]()

    original_finish = manager.finish_run

    calls = []

    def commit_then_disconnect(**kwargs):

        calls.append(kwargs)

        original_finish(**kwargs)

        raise psycopg.errors.ConnectionFailure(
            "Simulated connection loss after commit"
        )

    monkeypatch.setattr(
        manager,
        "finish_run",
        commit_then_disconnect,
    )

    result = recovery.finish_run(
        run_id=run_id,
        status="completed",
        received=0,
        checkpoint=advance(100),
        skip_unsafe_checkpoint=True,
    )

    assert len(calls) == 1

    assert result["metadata"][
        "checkpoint_finalization"
    ] == expected_receipt(100)

    assert context["get"]()[
        "last_successful_run_id"
    ] == run_id


def test_recovery_rejects_wrong_checkpoint_receipt(context):

    from scrapers.storage.run_recovery import (
        RunRecovery,
        RunRecoveryError,
    )

    from scrapers.storage.retry_policy import RetryPolicy

    run_id = context["start"]()

    context["finish"](run_id, advance(100))

    recovery = RunRecovery(
        context["manager"],
        RetryPolicy(),
    )

    with pytest.raises(
        RunRecoveryError,
        match="receipt mismatch",
    ):

        recovery.verify_finalization(
            run_id=run_id,
            status="completed",
            received=0,
            error_message=None,
            checkpoint=advance(999),
        )
