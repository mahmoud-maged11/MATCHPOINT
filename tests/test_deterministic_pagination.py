from datetime import datetime, timezone

import pytest

from scrapers.incremental_window import (
    IncrementalWindow,
    PaginationEvidence,
)


WINDOW = IncrementalWindow(
    lower=datetime(
        2026, 1, 1, tzinfo=timezone.utc
    ),
    upper=datetime(
        2027, 1, 1, tzinfo=timezone.utc
    ),
)


def record(source_id, modified="2026-08-21T12:42:49"):

    return {
        "id": source_id,
        "modified_gmt": modified,
    }


def evidence():

    return PaginationEvidence(
        WINDOW,
        2,
        ordering="id_asc",
    )


def first_page(validator):

    validator.observe(
        page=1,
        records=[record(10), record(20)],
        total=4,
        total_pages=2,
    )


def test_equal_modified_timestamps():

    validator = evidence()

    first_page(validator)

    validator.observe(
        page=2,
        records=[record(30), record(40)],
        total=4,
        total_pages=2,
    )

    assert validator.boundary_verified
    assert validator.seen_ids == {10, 20, 30, 40}


def test_non_monotonic_modified_timestamps():

    validator = evidence()

    validator.observe(
        page=1,
        records=[
            record(10, "2026-09-01T00:00:00"),
            record(20, "2026-02-01T00:00:00"),
        ],
        total=4,
        total_pages=2,
    )

    validator.observe(
        page=2,
        records=[
            record(30, "2026-11-01T00:00:00"),
            record(40, "2026-03-01T00:00:00"),
        ],
        total=4,
        total_pages=2,
    )

    assert validator.boundary_verified


@pytest.mark.parametrize(
    "records,message",
    [
        (
            [record(20), record(30)],
            "Repeated source ID",
        ),
        (
            [record(15), record(30)],
            "Source ID order changed",
        ),
        (
            [record(40), record(30)],
            "Source ID order changed",
        ),
        (
            [
                record(30),
                record(40, "2027-02-01T00:00:00"),
            ],
            "Record outside requested window",
        ),
    ],
)
def test_invalid_second_page(records, message):

    validator = evidence()

    first_page(validator)

    with pytest.raises(ValueError, match=message):

        validator.observe(
            page=2,
            records=records,
            total=4,
            total_pages=2,
        )

    assert validator.failed
    assert not validator.boundary_verified


def test_total_drift_still_rejected():

    validator = evidence()

    first_page(validator)

    with pytest.raises(
        ValueError,
        match="Record total changed",
    ):

        validator.observe(
            page=2,
            records=[record(30), record(40)],
            total=5,
            total_pages=3,
        )

    assert not validator.boundary_verified


def test_empty_window():

    validator = evidence()

    validator.observe(
        page=1,
        records=[],
        total=0,
        total_pages=0,
    )

    assert validator.boundary_verified


def test_last_partial_page():

    validator = evidence()

    validator.observe(
        page=1,
        records=[record(10), record(20)],
        total=3,
        total_pages=2,
    )

    validator.observe(
        page=2,
        records=[record(30)],
        total=3,
        total_pages=2,
    )

    assert validator.boundary_verified


def test_invalid_ordering_rejected():

    with pytest.raises(
        ValueError,
        match="Unsupported pagination ordering",
    ):

        PaginationEvidence(
            WINDOW,
            2,
            ordering="invalid",
        )


def test_legacy_modified_ordering_preserved():

    validator = PaginationEvidence(
        WINDOW,
        2,
    )

    validator.observe(
        page=1,
        records=[
            record(40, "2026-11-01T00:00:00"),
            record(10, "2026-10-01T00:00:00"),
        ],
        total=2,
        total_pages=1,
    )

    assert validator.boundary_verified
