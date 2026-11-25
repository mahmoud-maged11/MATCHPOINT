from datetime import datetime, timezone

from scrapers.utils.dates import (
    parse_source_datetime,
    normalize_source_datetime,
    resolve_opportunity_status
)


def test_parse_wuzzuf_date():
    assert parse_source_datetime(
        "11/25/2026 10:00:00"
    ) == datetime(2026, 11, 25, 10)


def test_invalid_date():
    assert parse_source_datetime("invalid") is None


def test_missing_date():
    assert parse_source_datetime(None) is None


def test_unknown_timezone():
    value, precision = normalize_source_datetime(
        "11/25/2026 10:00:00"
    )

    assert value is None
    assert precision == "unknown"


def test_known_timezone():
    value, precision = normalize_source_datetime(
        "2026-11-25T12:00:00+02:00"
    )

    assert value == datetime(
        2026, 11, 25, 10,
        tzinfo=timezone.utc
    )

    assert precision == "exact"


def test_definitely_expired():
    observed = datetime(
        2026, 11, 25, 10,
        tzinfo=timezone.utc
    )

    assert resolve_opportunity_status(
        "active",
        "11/24/2026 10:00:00",
        observed
    ) == "expired"


def test_uncertain_expiration():
    observed = datetime(
        2026, 11, 25, 10,
        tzinfo=timezone.utc
    )

    assert resolve_opportunity_status(
        "active",
        "11/25/2026 08:00:00",
        observed
    ) == "active"


def test_future_deadline():
    observed = datetime(
        2026, 11, 25,
        tzinfo=timezone.utc
    )

    assert resolve_opportunity_status(
        "active",
        "12/25/2026 10:00:00",
        observed
    ) == "active"


def test_closed_status_preserved():
    assert resolve_opportunity_status(
        "closed",
        None,
        datetime.now(timezone.utc)
    ) == "closed"


def test_missing_deadline_not_expired():
    assert resolve_opportunity_status(
        "active",
        None,
        datetime.now(timezone.utc)
    ) == "active"



def test_date_only_precision():

    value, precision = normalize_source_datetime(
        "2026-11-25"
    )

    assert value is None
    assert precision == "date_only"


def test_date_only_not_expired_early():

    observed = datetime(
        2026, 11, 25, 23, 59,
        tzinfo=timezone.utc
    )

    assert resolve_opportunity_status(
        "active",
        "2026-11-25",
        observed
    ) == "active"


def test_date_only_expired():

    observed = datetime(
        2026, 11, 26, 13,
        tzinfo=timezone.utc
    )

    assert resolve_opportunity_status(
        "active",
        "2026-11-25",
        observed
    ) == "expired"


def test_non_string_date():

    assert parse_source_datetime(12345) is None