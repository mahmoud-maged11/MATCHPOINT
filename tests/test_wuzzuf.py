from pathlib import Path
from decimal import Decimal

import pytest

from scrapers.sources.wuzzuf import WuzzufScraper


@pytest.fixture
def jobs():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "wuzzuf_synthetic.html"
    )

    return WuzzufScraper(str(fixture_path)).run()


def test_valid_cards_count(jobs):
    assert len(jobs) == 3


def test_source_identity(jobs):
    job = jobs[0]

    assert job.source_name == "wuzzuf"
    assert job.source_opportunity_id == "test001"
    assert str(job.source_url) == (
        "https://wuzzuf.net/jobs/p/test001-data-engineer"
    )


def test_basic_fields(jobs):
    job = jobs[0]

    assert job.title == "Data Engineer"
    assert job.organization == "Test Company"
    assert job.location == "Cairo, Egypt"
    assert job.opportunity_type == "job"


def test_single_employment_type(jobs):
    assert jobs[0].employment_types == ["full_time"]


def test_multiple_employment_types(jobs):
    assert jobs[1].employment_types == [
        "part_time",
        "freelance"
    ]


def test_work_modes(jobs):
    assert jobs[0].work_modes == ["remote"]
    assert jobs[1].work_modes == ["hybrid"]


def test_experience_levels(jobs):
    assert jobs[0].experience_level == "unknown"
    assert jobs[0].experience_level_raw == "Experienced"

    assert jobs[1].experience_level == "entry_level"
    assert jobs[1].experience_level_raw == "Entry Level"


def test_experience_ranges(jobs):
    assert jobs[0].experience_years_min == Decimal("2")
    assert jobs[0].experience_years_max == Decimal("5")

    assert jobs[1].experience_years_min == Decimal("0")
    assert jobs[1].experience_years_max == Decimal("2")


def test_categories(jobs):
    assert jobs[0].categories == [
        "IT/Software Development"
    ]


def test_required_skills(jobs):
    assert jobs[0].required_skills == [
        "Python",
        "SQL",
        "Apache Spark"
    ]


def test_publication_date_selectors(jobs):
    assert jobs[0].published_at_raw == "1 day ago"
    assert jobs[1].published_at_raw == "13 days ago"


def test_relative_date_precision(jobs):
    for job in jobs[:2]:
        assert job.published_at_precision == "relative"
        assert job.published_at is None


def test_missing_optional_fields(jobs):
    job = jobs[2]

    assert job.title == "Python Developer"
    assert job.organization is None
    assert job.location is None
    assert job.employment_types is None
    assert job.work_modes is None
    assert job.categories is None
    assert job.required_skills is None
    assert job.experience_level is None
    assert job.published_at_raw is None


def test_malformed_card_skipped(jobs):
    assert [job.source_opportunity_id for job in jobs] == [
        "test001",
        "test002",
        "test003"
    ]


def test_raw_payload_preserved(jobs):
    assert jobs[0].raw_payload["published_raw"] == "1 day ago"
    assert "card_html" in jobs[0].raw_payload
    assert "Data Engineer" in jobs[0].raw_payload["card_html"]


@pytest.fixture
def completed_scraper():

    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "wuzzuf_synthetic.html"
    )

    scraper = WuzzufScraper(str(fixture_path))

    scraper.run()

    return scraper

def test_invalid_records_count(completed_scraper):
    assert len(completed_scraper.invalid_records) == 2


def test_missing_required_field(completed_scraper):
    record = completed_scraper.invalid_records[0]

    assert record.error_type == "MissingRequiredField"
    assert record.source_url is None


def test_validation_error(completed_scraper):
    record = completed_scraper.invalid_records[1]

    assert record.error_type == "ValidationError"
    assert "Minimum experience" in record.error_message


def test_invalid_record_source_url(completed_scraper):
    record = completed_scraper.invalid_records[1]

    assert record.source_url == (
        "https://wuzzuf.net/jobs/p/test005-invalid-experience"
    )


def test_invalid_record_run_id(completed_scraper):
    for record in completed_scraper.invalid_records:
        assert record.run_id == completed_scraper.run_id


def test_invalid_record_raw_payload(completed_scraper):
    for record in completed_scraper.invalid_records:
        assert "card_html" in record.raw_payload
        assert record.raw_payload["card_html"]


def test_invalid_record_source_name(completed_scraper):
    for record in completed_scraper.invalid_records:
        assert record.source_name == "wuzzuf"


def test_invalid_record_timestamp(completed_scraper):
    for record in completed_scraper.invalid_records:
        assert record.collected_at.utcoffset().total_seconds() == 0