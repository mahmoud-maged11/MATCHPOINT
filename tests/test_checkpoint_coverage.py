import json

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest

from scrapers.checkpoint_intent import CheckpointIntent
from scrapers.checkpoint_coverage import (
    create_coverage_evidence,
    validate_coverage_evidence,
    result_digest,
)
from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)
from scrapers.storage.collection_snapshot import (
    CollectionSnapshotStore,
)

from test_egyincs_incremental import (
    WINDOW,
    scraper_for,
    record,
    response,
)


@pytest.fixture
def context():

    scraper = scraper_for()

    scraper.fetch = Mock(
        side_effect=[
            response(
                [record(1), record(2)],
                3,
                2,
            ),
            response(
                [record(3)],
                3,
                2,
            ),
        ]
    )

    result = scraper.run_with_result()

    intent = CheckpointIntent(
        run_id=result.run_id,
        source_name="egyincs",
        collection_scope="jobs",
        previous_run_id=uuid4(),
        previous_watermark=(
            WINDOW.lower + timedelta(minutes=5)
        ),
        window=WINDOW,
    )

    return scraper, result, intent


def create(context):

    scraper, result, intent = context

    return create_coverage_evidence(
        intent=intent,
        result=result,
        scraper=scraper,
    )


def validate(context, metadata):

    _, result, intent = context

    return validate_coverage_evidence(
        intent=intent,
        result=result,
        metadata=metadata,
    )


def test_complete_coverage(context):

    metadata = create(context)

    assert metadata is not None
    assert metadata["accepted_count"] == 3
    assert metadata["pages_seen"] == 2

    assert validate(context, metadata)


def test_metadata_roundtrip(context):

    metadata = json.loads(
        json.dumps(create(context))
    )

    assert validate(context, metadata)


def test_missing_evidence(context):

    assert not validate(context, None)


def test_snapshot_roundtrip(context, tmp_path):

    _, result, intent = context

    metadata = create(context)

    store = CollectionSnapshotStore(
        tmp_path / "snapshots",
        integrity_key=b"x" * 32,
    )

    store.save(result)

    restored = store.load(result.run_id)

    assert result_digest(restored) == result_digest(result)

    assert validate_coverage_evidence(
        intent=intent,
        result=restored,
        metadata=metadata,
    )


def test_changed_result_rejected(context):

    _, result, intent = context

    metadata = create(context)

    changed = replace(
        result,
        opportunities=result.opportunities[:-1],
    )

    with pytest.raises(ValueError, match="digest mismatch"):

        validate_coverage_evidence(
            intent=intent,
            result=changed,
            metadata=metadata,
        )


def test_changed_payload_rejected(context):

    _, result, intent = context

    metadata = create(context)

    changed_item = result.opportunities[0].model_copy(
        update={"title": "Changed title"}
    )

    changed = replace(
        result,
        opportunities=(
            changed_item,
            *result.opportunities[1:],
        ),
    )

    with pytest.raises(ValueError, match="digest mismatch"):

        validate_coverage_evidence(
            intent=intent,
            result=changed,
            metadata=metadata,
        )


def test_changed_intent_rejected(context):

    _, result, intent = context

    metadata = create(context)

    changed = replace(
        intent,
        previous_run_id=uuid4(),
    )

    with pytest.raises(ValueError, match="Intent digest"):

        validate_coverage_evidence(
            intent=changed,
            result=result,
            metadata=metadata,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("version", 2),
        ("intent_sha256", "invalid"),
        ("result_sha256", "0" * 64),
        ("accepted_count", 2),
        ("accepted_count", True),
        ("expected_total", 4),
        ("expected_pages", 3),
        ("pages_seen", 1),
        ("page_size", 0),
        ("page_size", -1),
    ],
)
def test_invalid_metadata(context, field, value):

    metadata = create(context)
    metadata[field] = value

    with pytest.raises(ValueError):

        validate(context, metadata)


def test_unknown_field(context):

    metadata = create(context)
    metadata["extra"] = True

    with pytest.raises(ValueError):

        validate(context, metadata)


def test_missing_field(context):

    metadata = create(context)
    del metadata["pages_seen"]

    with pytest.raises(ValueError):

        validate(context, metadata)


def test_wrong_result_instance(context):

    scraper, result, intent = context

    with pytest.raises(ValueError, match="result mismatch"):

        create_coverage_evidence(
            intent=intent,
            result=replace(result),
            scraper=scraper,
        )


def test_wrong_endpoint(context):

    scraper, result, intent = context

    changed = replace(
        intent,
        collection_scope="lp_course",
    )

    with pytest.raises(ValueError, match="binding mismatch"):

        create_coverage_evidence(
            intent=changed,
            result=result,
            scraper=scraper,
        )


@pytest.mark.parametrize("limited", [False, True])
def test_empty_or_limited_window(limited):

    scraper = scraper_for(
        max_pages=1 if limited else None
    )

    scraper.fetch = Mock(
        return_value=(
            response(
                [record(1), record(2)],
                3,
                2,
            )
            if limited
            else response([], 0, 0)
        )
    )

    result = scraper.run_with_result()

    intent = CheckpointIntent(
        run_id=result.run_id,
        source_name="egyincs",
        collection_scope="jobs",
        previous_run_id=uuid4(),
        previous_watermark=(
            WINDOW.lower + timedelta(minutes=5)
        ),
        window=WINDOW,
    )

    metadata = create_coverage_evidence(
        intent=intent,
        result=result,
        scraper=scraper,
    )

    if limited:

        assert metadata is None

    else:

        assert metadata["accepted_count"] == 0
        assert metadata["pages_seen"] == 1

        assert validate_coverage_evidence(
            intent=intent,
            result=result,
            metadata=metadata,
        )
