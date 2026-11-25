import pytest

from datetime import datetime, timezone, timedelta

from scrapers.models import Opportunity
from scrapers.utils.hashing import generate_content_hash


@pytest.fixture
def valid_data():
    return {
        "source_name": "wuzzuf",
        "source_opportunity_id": "test123",
        "source_url": "https://wuzzuf.net/jobs/p/test123",
        "title": "Data Engineer",
        "organization": "Test Company",
        "opportunity_type": "job",
        "employment_types": ["full_time", "part_time"],
        "work_modes": ["remote", "hybrid"],
        "categories": ["IT", "Engineering"],
        "required_skills": ["Python", "SQL", "AWS"],
        "published_at_raw": "1 day ago",
        "published_at_precision": "relative",
        "raw_payload": {}
    }



def test_same_content_same_hash(valid_data):
    first = Opportunity(**valid_data)
    second = Opportunity(**valid_data)

    assert generate_content_hash(first) == generate_content_hash(second)


def test_array_order_does_not_change_hash(valid_data):
    first = Opportunity(**valid_data)

    reordered_data = valid_data.copy()

    for field in (
        "required_skills",
        "categories",
        "employment_types",
        "work_modes"
    ):
        reordered_data[field] = list(
            reversed(valid_data[field])
        )

    second = Opportunity(**reordered_data)

    assert generate_content_hash(first) == generate_content_hash(second)



def test_collection_time_does_not_change_hash(valid_data):
    first_time = datetime.now(timezone.utc)

    first = Opportunity(
        **valid_data,
        collected_at=first_time
    )

    second = Opportunity(
        **valid_data,
        collected_at=first_time + timedelta(days=1)
    )

    assert generate_content_hash(first) == generate_content_hash(second)



def test_relative_date_does_not_change_hash(valid_data):
    first = Opportunity(**valid_data)

    updated_data = valid_data.copy()
    updated_data["published_at_raw"] = "2 days ago"

    second = Opportunity(**updated_data)

    assert generate_content_hash(first) == generate_content_hash(second)



def test_content_change_changes_hash(valid_data):
    first = Opportunity(**valid_data)

    updated_data = valid_data.copy()
    updated_data["title"] = "Senior Data Engineer"

    second = Opportunity(**updated_data)

    assert generate_content_hash(first) != generate_content_hash(second)


def test_source_metadata_does_not_change_hash(valid_data):
    first = Opportunity(**valid_data)

    updated_data = valid_data.copy()

    updated_data["source_name"] = "bayt"
    updated_data["source_opportunity_id"] = "test456"
    updated_data["source_url"] = "https://www.bayt.com/jobs/test456"
    updated_data["raw_payload"] = {"html": "different HTML"}

    second = Opportunity(**updated_data)

    assert generate_content_hash(first) == generate_content_hash(second)


def test_exact_date_change_changes_hash(valid_data):
    first_data = valid_data.copy()

    first_data["published_at_precision"] = "exact"
    first_data["published_at_raw"] = None
    first_data["published_at"] = datetime(
        2026, 11, 20, 10, 0, tzinfo=timezone.utc
    )

    first = Opportunity(**first_data)

    second_data = first_data.copy()
    second_data["published_at"] += timedelta(days=1)

    second = Opportunity(**second_data)

    assert generate_content_hash(first) != generate_content_hash(second)


def test_null_and_empty_array_have_different_hashes(valid_data):
    first_data = valid_data.copy()
    first_data["required_skills"] = None

    second_data = valid_data.copy()
    second_data["required_skills"] = []

    first = Opportunity(**first_data)
    second = Opportunity(**second_data)

    assert generate_content_hash(first) != generate_content_hash(second)


def test_relative_deadline_does_not_change_hash(valid_data):
    first_data = valid_data.copy()
    first_data["deadline_raw"] = "5 days left"
    first_data["deadline_precision"] = "relative"

    second_data = first_data.copy()
    second_data["deadline_raw"] = "4 days left"

    first = Opportunity(**first_data)
    second = Opportunity(**second_data)

    assert generate_content_hash(first) == generate_content_hash(second)


def test_skill_change_changes_hash(valid_data):
    first = Opportunity(**valid_data)

    updated_data = valid_data.copy()
    updated_data["required_skills"] = [
        "Python", "SQL", "AWS", "Apache Spark"
    ]

    second = Opportunity(**updated_data)

    assert generate_content_hash(first) != generate_content_hash(second)



def test_equivalent_decimal_hash(valid_data):

    first = Opportunity(
        **valid_data,
        salary_min="5000"
    )

    second = Opportunity(
        **valid_data,
        salary_min="5000.00"
    )

    assert (
        generate_content_hash(first)
        == generate_content_hash(second)
    )


def test_salary_period_changes_hash(valid_data):

    first = Opportunity(
        **valid_data,
        salary_period="monthly"
    )

    second = Opportunity(
        **valid_data,
        salary_period="yearly"
    )

    assert (
        generate_content_hash(first)
        != generate_content_hash(second)
    )