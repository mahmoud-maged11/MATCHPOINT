from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from scrapers.models import Opportunity


TIMESTAMP = datetime(
    2026, 11, 27, 12, 0,
    tzinfo=timezone.utc
)


def make_opportunity(**kwargs):

    return Opportunity(
        source_name="wuzzuf",
        source_opportunity_id="audit-date-test",
        source_url="https://wuzzuf.net/jobs/p/test",
        title="Data Engineer",
        opportunity_type="job",
        raw_payload={"test": True},
        **kwargs,
    )


@pytest.mark.parametrize(
    "field",
    ["published_at", "deadline"],
)
def test_date_only_rejects_timestamp(field):

    with pytest.raises(
        ValidationError,
        match="date_only cannot contain a timestamp",
    ):
        make_opportunity(**{
            field: TIMESTAMP,
            f"{field}_raw": "2026-11-27",
            f"{field}_precision": "date_only",
        })


@pytest.mark.parametrize(
    "field",
    ["published_at", "deadline"],
)
@pytest.mark.parametrize(
    "precision",
    ["relative", "date_only"],
)
@pytest.mark.parametrize(
    "raw",
    [None, "", " ", "\t\n", "\u00a0"],
)
def test_date_precision_requires_nonblank_raw(
    field,
    precision,
    raw,
):

    with pytest.raises(
        ValidationError,
        match="requires its original date value",
    ):
        make_opportunity(**{
            f"{field}_raw": raw,
            f"{field}_precision": precision,
        })


@pytest.mark.parametrize(
    "field",
    ["published_at", "deadline"],
)
@pytest.mark.parametrize(
    "precision,value,raw",
    [
        (None, None, None),
        ("unknown", None, "Unavailable"),
        ("date_only", None, "2026-11-27"),
        ("exact", TIMESTAMP, None),
        ("relative", TIMESTAMP, "2 hours ago"),
        ("relative", None, "Recently"),
    ],
)
def test_valid_date_combinations(
    field,
    precision,
    value,
    raw,
):

    opportunity = make_opportunity(**{
        field: value,
        f"{field}_raw": raw,
        f"{field}_precision": precision,
    })

    assert getattr(opportunity, field) == value

    assert getattr(
        opportunity,
        f"{field}_precision",
    ) == precision

    assert getattr(
        opportunity,
        f"{field}_raw",
    ) == raw
