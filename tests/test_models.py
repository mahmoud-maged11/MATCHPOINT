import pytest

from datetime import datetime, timezone, timedelta
from pydantic import ValidationError
from scrapers.models import Opportunity


@pytest.fixture
def valid_data():
    return {
        "source_name": "wuzzuf",
        "source_url": "https://wuzzuf.net/jobs/p/test",
        "title": "Data Engineer",
        "opportunity_type": "job",
        "raw_payload": {}
    }


def test_valid_opportunity(valid_data):
    opportunity = Opportunity(**valid_data)

    assert opportunity.title == "Data Engineer"
    assert opportunity.status == "unknown"


def test_empty_title(valid_data):
    valid_data["title"] = "   "

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)


def test_invalid_currency(valid_data):
    valid_data["currency"] = "ABC"

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)


def test_currency_normalization(valid_data):
    valid_data["currency"] = "egp"

    opportunity = Opportunity(**valid_data)

    assert opportunity.currency == "EGP"


def test_negative_salary(valid_data):
    valid_data["salary_min"] = -5000

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)


def test_invalid_salary_range(valid_data):
    valid_data["salary_min"] = 20000
    valid_data["salary_max"] = 10000

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)


def test_invalid_experience_range(valid_data):
    valid_data["experience_years_min"] = 5
    valid_data["experience_years_max"] = 2

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)


def test_negative_experience(valid_data):
    valid_data["experience_years_min"] = -2

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)


def test_multiple_employment_types(valid_data):
    valid_data["employment_types"] = [
        "part_time",
        "freelance",
        "part_time"
    ]

    opportunity = Opportunity(**valid_data)

    assert opportunity.employment_types == [
        "part_time",
        "freelance"
    ]


def test_multiple_work_modes(valid_data):
    valid_data["work_modes"] = [
        "remote",
        "hybrid"
    ]

    opportunity = Opportunity(**valid_data)

    assert opportunity.work_modes == [
        "remote",
        "hybrid"
    ]


def test_invalid_work_mode(valid_data):
    valid_data["work_modes"] = ["invalid"]

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)


def test_unknown_with_known_values(valid_data):
    valid_data["work_modes"] = [
        "unknown",
        "remote"
    ]

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)


def test_duplicate_skills(valid_data):
    valid_data["required_skills"] = [
        "Python",
        "SQL",
        "python"
    ]

    opportunity = Opportunity(**valid_data)

    assert opportunity.required_skills == [
        "Python",
        "SQL"
    ]


def test_naive_timestamp(valid_data):
    valid_data["published_at"] = datetime(
        2026, 11, 24
    )

    valid_data["published_at_precision"] = "exact"

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)


def test_utc_normalization(valid_data):
    valid_data["published_at"] = datetime(
        2026, 11, 24, 12, 0,
        tzinfo=timezone(timedelta(hours=2))
    )

    valid_data["published_at_precision"] = "exact"

    opportunity = Opportunity(**valid_data)

    assert opportunity.published_at == datetime(
        2026, 11, 24, 10, 0,
        tzinfo=timezone.utc
    )


def test_relative_date(valid_data):
    valid_data["published_at_raw"] = "1 day ago"
    valid_data["published_at_precision"] = "relative"

    opportunity = Opportunity(**valid_data)

    assert opportunity.published_at is None
    assert opportunity.published_at_raw == "1 day ago"


def test_relative_date_without_raw(valid_data):
    valid_data["published_at_precision"] = "relative"

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)


def test_exact_date_without_timestamp(valid_data):
    valid_data["published_at_precision"] = "exact"

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)


def test_date_only_deadline(valid_data):
    valid_data["deadline_raw"] = "2026-12-15"
    valid_data["deadline_precision"] = "date_only"

    opportunity = Opportunity(**valid_data)

    assert opportunity.deadline is None
    assert opportunity.deadline_raw == "2026-12-15"


def test_reject_legacy_field(valid_data):
    valid_data["employment_type"] = "full_time"

    with pytest.raises(ValidationError):
        Opportunity(**valid_data)