import os

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest

from scrapers.incremental_window import IncrementalWindow

from scrapers.storage.checkpoints import (
    CheckpointError,
    ConcurrentCheckpointError,
)

from scrapers.storage.run_recovery import (
    RunRecovery,
    RunRecoveryError,
)

from scrapers.storage.retry_policy import RetryPolicy

from test_checkpoint_persistence import (
    context,
    advance,
    expected_receipt,
)

from test_incremental_pipeline import (
    pipeline,
    execute,
    make_scraper,
)


pytestmark = pytest.mark.skipif(
    os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1",
    reason="Requires isolated PostgreSQL database",
)


def finish_conflict(context, run_id, checkpoint):

    return context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=0,
        checkpoint=checkpoint,
        skip_checkpoint_conflict=True,
    )


def assert_conflict_receipt(
    row,
    value,
    previous=None,
):

    assert row["status"] == "completed"

    assert row["metadata"][
        "checkpoint_finalization"
    ] == expected_receipt(
        value,
        previous,
        "skipped_checkpoint_conflict",
    )


def test_concurrent_initial_checkpoint(context):

    winner = context["start"]()
    loser = context["start"]()

    context["finish"](winner, advance(100))

    before = context["get"]()

    result = finish_conflict(
        context,
        loser,
        advance(200),
    )

    assert_conflict_receipt(result, 200)

    assert context["get"]() == before


def test_concurrent_checkpoint_update(context):

    initial = context["start"]()

    context["finish"](initial, advance(100))

    winner = context["start"]()
    loser = context["start"]()

    context["finish"](
        winner,
        advance(200, initial),
    )

    before = context["get"]()

    result = finish_conflict(
        context,
        loser,
        advance(300, initial),
    )

    assert_conflict_receipt(
        result,
        300,
        initial,
    )

    assert context["get"]() == before

    assert before["last_successful_run_id"] == winner


def test_strict_conflict_rolls_back(context):

    winner = context["start"]()
    loser = context["start"]()

    context["finish"](winner, advance(100))

    before_run = context["manager"].get_run(loser)
    before_checkpoint = context["get"]()

    with pytest.raises(ConcurrentCheckpointError):

        context["finish"](
            loser,
            advance(200),
        )

    assert context["manager"].get_run(
        loser
    ) == before_run

    assert context["get"]() == before_checkpoint


def test_backward_checkpoint_not_silently_skipped(context):

    initial = context["start"]()

    context["finish"](initial, advance(100))

    run_id = context["start"]()

    before_run = context["manager"].get_run(run_id)
    before_checkpoint = context["get"]()

    with pytest.raises(
        CheckpointError,
        match="cannot move backwards",
    ) as error:

        finish_conflict(
            context,
            run_id,
            advance(50, initial),
        )

    assert not isinstance(
        error.value,
        ConcurrentCheckpointError,
    )

    assert context["manager"].get_run(
        run_id
    ) == before_run

    assert context["get"]() == before_checkpoint


def test_conflict_receipt_after_ambiguous_commit(
    context,
    monkeypatch,
):

    winner = context["start"]()
    loser = context["start"]()

    context["finish"](winner, advance(100))

    manager = context["manager"]

    recovery = RunRecovery(
        manager,
        RetryPolicy(),
    )

    original_finish = manager.finish_run

    calls = []

    def commit_then_disconnect(**kwargs):

        calls.append(kwargs)

        original_finish(**kwargs)

        raise psycopg.errors.ConnectionFailure(
            "Simulated disconnect after conflict receipt commit"
        )

    monkeypatch.setattr(
        manager,
        "finish_run",
        commit_then_disconnect,
    )

    before = context["get"]()

    result = recovery.finish_run(
        run_id=loser,
        status="completed",
        received=0,
        checkpoint=advance(200),
        skip_checkpoint_conflict=True,
    )

    assert len(calls) == 1

    assert_conflict_receipt(result, 200)

    assert context["get"]() == before


def test_conflict_receipt_requires_explicit_permission(
    context,
):

    winner = context["start"]()
    loser = context["start"]()

    context["finish"](winner, advance(100))

    finish_conflict(
        context,
        loser,
        advance(200),
    )

    recovery = RunRecovery(
        context["manager"],
        RetryPolicy(),
    )

    with pytest.raises(
        RunRecoveryError,
        match="receipt mismatch",
    ):

        recovery.verify_finalization(
            run_id=loser,
            status="completed",
            received=0,
            error_message=None,
            checkpoint=advance(200),
        )


def next_intent(pipeline):

    previous = pipeline["intent"].target_watermark

    return replace(
        pipeline["intent"],
        run_id=uuid4(),
        previous_run_id=pipeline["run_id"],
        previous_watermark=previous,
        window=IncrementalWindow.from_checkpoint(
            previous,
            now=previous + timedelta(hours=1),
        ),
    )


def test_correct_previous_watermark(pipeline):

    execute(
        pipeline,
        make_scraper(empty=True),
    )

    before = pipeline["checkpoint"]()

    intent = next_intent(pipeline)

    pipeline["orchestrator"].validate_previous_checkpoint(
        intent
    )

    assert pipeline["checkpoint"]() == before


def test_incorrect_previous_watermark(pipeline):

    execute(
        pipeline,
        make_scraper(empty=True),
    )

    before = pipeline["checkpoint"]()

    intent = next_intent(pipeline)

    incorrect = replace(
        intent,
        previous_watermark=(
            intent.previous_watermark
            + timedelta(seconds=1)
        ),
    )

    with pytest.raises(
        CheckpointError,
        match="Previous watermark mismatch",
    ):

        pipeline["orchestrator"].validate_previous_checkpoint(
            incorrect
        )

    assert pipeline["checkpoint"]() == before


def test_stale_previous_run_id(pipeline):

    execute(
        pipeline,
        make_scraper(empty=True),
    )

    before = pipeline["checkpoint"]()

    intent = replace(
        next_intent(pipeline),
        previous_run_id=uuid4(),
    )

    with pytest.raises(ConcurrentCheckpointError):

        pipeline["orchestrator"].validate_previous_checkpoint(
            intent
        )

    assert pipeline["checkpoint"]() == before


def test_missing_expected_checkpoint(pipeline):

    intent = replace(
        pipeline["intent"],
        previous_run_id=uuid4(),
    )

    with pytest.raises(
        ConcurrentCheckpointError,
        match="Expected checkpoint does not exist",
    ):

        pipeline["orchestrator"].validate_previous_checkpoint(
            intent
        )

    assert pipeline["checkpoint"]() is None
