from datetime import datetime, timedelta, timezone

import pytest

from scrapers.incremental_window import (
    IncrementalWindow,
    PaginationEvidence,
    parse_modified_gmt,
)


UTC = timezone.utc

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)

CHECKPOINT = NOW - timedelta(hours=1)

WINDOW = IncrementalWindow.from_checkpoint(
    CHECKPOINT,
    now=NOW,
)


def record(source_id, minute=30):

    return {
        "id": source_id,
        "modified_gmt": (
            f"2026-11-27T11:{minute:02d}:00"
        ),
    }


def test_safe_window():

    assert WINDOW.lower == CHECKPOINT - timedelta(minutes=5)

    assert WINDOW.upper == NOW - timedelta(minutes=2)

    assert WINDOW.api_params() == {
        "modified_after": "2026-11-27T10:55:00Z",
        "modified_before": "2026-11-27T11:58:00Z",
        "orderby": "modified",
        "order": "desc",
    }


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-27T11:30:00",
        "2026-11-27T11:30:00Z",
        "2026-11-27T11:30:00+00:00",
    ],
)
def test_valid_gmt(value):

    assert parse_modified_gmt(value) == datetime(
        2026, 11, 27, 11, 30, tzinfo=UTC
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        123,
        "2026-11-27",
        "2026-02-30T11:30:00",
        "2026-11-27T11:30:00+02:00",
        "0000-00-00T00:00:00",
        "yesterday",
    ],
)
def test_invalid_gmt(value):

    with pytest.raises(ValueError):
        parse_modified_gmt(value)


@pytest.mark.parametrize(
    "checkpoint",
    [
        NOW + timedelta(hours=1),
        NOW,
        NOW - timedelta(minutes=1),
        NOW.replace(tzinfo=None),
    ],
)
def test_unsafe_checkpoint(checkpoint):

    with pytest.raises(ValueError):

        IncrementalWindow.from_checkpoint(
            checkpoint,
            now=NOW,
        )


@pytest.mark.parametrize(
    "overlap,lag",
    [
        (timedelta(0), timedelta(minutes=2)),
        (timedelta(seconds=-1), timedelta(0)),
        (timedelta(minutes=5), timedelta(seconds=-1)),
    ],
)
def test_invalid_durations(overlap, lag):

    with pytest.raises(ValueError):

        IncrementalWindow.from_checkpoint(
            CHECKPOINT,
            now=NOW,
            overlap=overlap,
            safety_lag=lag,
        )


def test_window_boundaries():

    assert WINDOW.contains(WINDOW.lower)
    assert WINDOW.contains(WINDOW.upper)

    assert not WINDOW.contains(
        WINDOW.lower - timedelta(seconds=1)
    )

    assert not WINDOW.contains(
        WINDOW.upper + timedelta(seconds=1)
    )


def test_complete_pagination():

    evidence = PaginationEvidence(WINDOW, 2)

    evidence.observe(
        page=1,
        records=[record(1), record(2)],
        total=3,
        total_pages=2,
    )

    assert not evidence.boundary_verified

    evidence.observe(
        page=2,
        records=[record(3, 29)],
        total=3,
        total_pages=2,
    )

    assert evidence.boundary_verified
    assert evidence.seen_ids == {1, 2, 3}


def test_empty_window():

    evidence = PaginationEvidence(WINDOW, 20)

    evidence.observe(
        page=1,
        records=[],
        total=0,
        total_pages=0,
    )

    assert evidence.boundary_verified


def test_equal_timestamps_across_pages():

    evidence = PaginationEvidence(WINDOW, 1)

    for page in range(1, 4):

        evidence.observe(
            page=page,
            records=[record(page)],
            total=3,
            total_pages=3,
        )

    assert evidence.boundary_verified


@pytest.mark.parametrize(
    "records,total,pages,page",
    [
        ([record(1)], 3, 2, 1),
        ([record(1), record(1)], 2, 1, 1),
        ([record(1), record(2, 31)], 2, 1, 1),
        ([record(1)], 1, 2, 1),
        ([record(1)], 1, 1, 2),
        ([], 1, 1, 1),
        ([record(1)], 0, 0, 1),
        ([{"id": 1}], 1, 1, 1),
        ([{"id": True}], 1, 1, 1),
        ([record(1)], None, 1, 1),
        ([record(1)], 1, None, 1),
        ([record(1, 59)], 1, 1, 1),
    ],
)
def test_invalid_page(records, total, pages, page):

    evidence = PaginationEvidence(WINDOW, 2)

    with pytest.raises(ValueError):

        evidence.observe(
            page=page,
            records=records,
            total=total,
            total_pages=pages,
        )

    assert evidence.failed
    assert not evidence.boundary_verified


@pytest.mark.parametrize(
    "records,total,pages",
    [
        ([record(1)], 2, 2),
        ([record(2, 31)], 2, 2),
        ([record(2)], 3, 3),
    ],
)
def test_cross_page_drift(records, total, pages):

    evidence = PaginationEvidence(WINDOW, 1)

    evidence.observe(
        page=1,
        records=[record(1)],
        total=2,
        total_pages=2,
    )

    with pytest.raises(ValueError):

        evidence.observe(
            page=2,
            records=records,
            total=total,
            total_pages=pages,
        )

    assert not evidence.boundary_verified


def test_failure_cannot_be_reset_by_valid_page():

    evidence = PaginationEvidence(WINDOW, 1)

    with pytest.raises(ValueError):

        evidence.observe(
            page=1,
            records=[],
            total=1,
            total_pages=1,
        )

    with pytest.raises(ValueError):

        evidence.observe(
            page=1,
            records=[record(1)],
            total=1,
            total_pages=1,
        )

    assert not evidence.boundary_verified


def test_missing_pages_cannot_verify_boundary():

    evidence = PaginationEvidence(WINDOW, 1)

    evidence.observe(
        page=1,
        records=[record(1)],
        total=2,
        total_pages=2,
    )

    assert not evidence.boundary_verified
