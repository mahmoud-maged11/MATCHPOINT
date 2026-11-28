import json

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from scrapers.checkpoint_intent import CheckpointIntent
from scrapers.incremental_window import IncrementalWindow


NOW = datetime(
    2026, 11, 27, 12, 0,
    tzinfo=timezone.utc,
)

PREVIOUS = NOW - timedelta(hours=1)


@pytest.fixture
def intent():

    return CheckpointIntent(
        run_id=uuid4(),
        source_name="egyincs",
        collection_scope="jobs",
        previous_run_id=uuid4(),
        previous_watermark=PREVIOUS,
        window=IncrementalWindow.from_checkpoint(
            PREVIOUS,
            now=NOW,
        ),
    )


def test_intent_roundtrip(intent):

    metadata = json.loads(
        json.dumps(intent.to_metadata())
    )

    assert CheckpointIntent.from_metadata(
        metadata
    ) == intent


def test_target_watermark(intent):

    assert intent.target_watermark == (
        NOW - timedelta(minutes=2)
    )


def test_bootstrap_intent(intent):

    bootstrap = replace(
        intent,
        previous_run_id=None,
    )

    assert CheckpointIntent.from_metadata(
        bootstrap.to_metadata()
    ) == bootstrap


def test_course_scope(intent):

    course = replace(
        intent,
        collection_scope="lp_course",
    )

    assert CheckpointIntent.from_metadata(
        course.to_metadata()
    ) == course


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "invalid"),
        ("previous_run_id", "invalid"),
        ("source_name", "wuzzuf"),
        ("collection_scope", "all"),
        ("collection_scope", "default"),
        ("window", None),
        ("previous_watermark", NOW),
        (
            "previous_watermark",
            PREVIOUS - timedelta(days=1),
        ),
        (
            "previous_watermark",
            PREVIOUS.replace(tzinfo=None),
        ),
        (
            "previous_watermark",
            PREVIOUS.replace(microsecond=1),
        ),
    ],
)
def test_invalid_intent(intent, field, value):

    with pytest.raises((TypeError, ValueError)):
        replace(intent, **{field: value})


def test_self_referencing_run(intent):

    with pytest.raises(ValueError):
        replace(
            intent,
            previous_run_id=intent.run_id,
        )


@pytest.mark.parametrize(
    "version",
    [0, 2, True, "1", None],
)
def test_invalid_metadata_version(intent, version):

    metadata = intent.to_metadata()

    metadata["version"] = version

    with pytest.raises(ValueError):
        CheckpointIntent.from_metadata(metadata)


def test_missing_metadata_field(intent):

    metadata = intent.to_metadata()

    del metadata["window_upper"]

    with pytest.raises(ValueError):
        CheckpointIntent.from_metadata(metadata)


def test_unknown_metadata_field(intent):

    metadata = intent.to_metadata()

    metadata["extra"] = True

    with pytest.raises(ValueError):
        CheckpointIntent.from_metadata(metadata)


def test_noncanonical_timestamp(intent):

    metadata = intent.to_metadata()

    metadata["window_upper"] = metadata[
        "window_upper"
    ].replace("Z", "+00:00")

    with pytest.raises(ValueError):
        CheckpointIntent.from_metadata(metadata)


def test_valid_binding(intent):

    intent.validate_binding(
        run_id=intent.run_id,
        source_name=intent.source_name,
        collection_scope=intent.collection_scope,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", uuid4()),
        ("source_name", "wuzzuf"),
        ("collection_scope", "lp_course"),
    ],
)
def test_invalid_binding(intent, field, value):

    arguments = {
        "run_id": intent.run_id,
        "source_name": intent.source_name,
        "collection_scope": intent.collection_scope,
    }

    arguments[field] = value

    with pytest.raises(
        ValueError,
        match="binding mismatch",
    ):
        intent.validate_binding(**arguments)


@pytest.mark.parametrize("value", [None, [], "invalid"])
def test_invalid_metadata_type(value):

    with pytest.raises(TypeError):
        CheckpointIntent.from_metadata(value)
