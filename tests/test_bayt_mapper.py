
import json

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from scrapers.sources.bayt_mapper import BaytMapper


URL = (
    "https://www.bayt.com/en/egypt/jobs/"
    "data-engineer-1234567/"
)

OBSERVED_AT = datetime(
    2026, 11, 25, tzinfo=timezone.utc
)


def make_posting(**overrides):

    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Data Engineer",
        "description": "<p>Build data pipelines.</p>",
        "identifier": {
            "@type": "PropertyValue",
            "value": "987654",
        },
        "hiringOrganization": {
            "name": "Example Company",
        },
        "jobLocation": {
            "address": {
                "addressCountry": "EG",
                "addressLocality": "Cairo",
            }
        },
        "employmentType": "FULL_TIME",
        "datePosted": "2026-11-20",
        "validThrough": "2026-12-20",
        "directApply": True,
    }

    posting.update(overrides)

    return posting


def make_html(posting=None, extra=""):

    if posting is None:
        posting = make_posting()

    return f"""
    <html>
        <head>
            <script type="application/ld+json">
                {json.dumps(posting)}
            </script>
        </head>
        <body>
            {extra}
        </body>
    </html>
    """


def map_job(posting=None, extra="", listing=None):

    return BaytMapper.map_job(
        URL,
        make_html(posting, extra),
        listing=listing,
        observed_at=OBSERVED_AT,
    )


def test_basic_mapping():

    result = map_job()

    assert result.source_name == "bayt"
    assert result.source_opportunity_id == "1234567"
    assert result.title == "Data Engineer"
    assert result.organization == "Example Company"
    assert result.location == "Cairo, Egypt"
    assert result.opportunity_type == "job"
    assert result.employment_types == ["full_time"]


def test_url_identity_over_json_identifier():

    result = map_job()

    assert result.source_opportunity_id == "1234567"
    assert result.raw_payload["identifier_value"] == "987654"


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "https://www.bayt.com/en/egypt/jobs/job-1234567/",
            "1234567",
        ),
        (
            "https://www.bayt.com/en/egypt/jobs/job-12345678/",
            "12345678",
        ),
        (
            "https://www.bayt.com/en/egypt/jobs/مهندس-123/",
            "123",
        ),
        (
            "https://www.bayt.com/en/egypt/jobs/%D9%85-123/",
            "123",
        ),
    ],
)
def test_valid_job_ids(url, expected):

    assert BaytMapper.extract_job_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://www.bayt.com/en/egypt/jobs/job-123/",
        "https://example.com/en/egypt/jobs/job-123/",
        "https://www.bayt.com/en/uae/jobs/job-123/",
        "https://www.bayt.com/en/egypt/jobs/job-0/",
        "https://www.bayt.com/en/egypt/jobs/job-123/?x=1",
        "https://www.bayt.com/en/egypt/jobs/job-123/#apply",
        "https://www.bayt.com/en/egypt/jobs/",
    ],
)
def test_invalid_job_urls(url):

    with pytest.raises(ValueError):
        BaytMapper.extract_job_id(url)


def test_missing_job_posting():

    with pytest.raises(ValueError):

        BaytMapper.map_job(
            URL,
            "<html></html>",
            observed_at=OBSERVED_AT,
        )


def test_multiple_job_postings():

    posting = [
        make_posting(),
        make_posting(title="Another Job"),
    ]

    with pytest.raises(ValueError):
        map_job(posting)


def test_graph_job_posting():

    result = map_job({
        "@graph": [
            {"@type": "Organization"},
            make_posting(),
        ]
    })

    assert result.title == "Data Engineer"


def test_missing_title():

    with pytest.raises(ValueError):
        map_job(make_posting(title=" "))


@pytest.mark.parametrize(
    "name",
    [
        "Confidential",
        "Confidential Company",
        "Anonymous",
        "Undisclosed",
    ],
)
def test_confidential_organization(name):

    result = map_job(
        make_posting(
            hiringOrganization={"name": name}
        )
    )

    assert result.organization is None


def test_non_egypt_location():

    result = map_job(
        make_posting(
            jobLocation={
                "address": {
                    "addressCountry": "SA",
                    "addressLocality": "Riyadh",
                }
            }
        )
    )

    assert result is None


def test_missing_location():

    assert map_job(
        make_posting(jobLocation=None)
    ) is None


def test_multiple_locations():

    result = map_job(
        make_posting(
            jobLocation=[
                {
                    "address": {
                        "addressCountry": "Egypt",
                        "addressLocality": "Cairo",
                    }
                },
                {
                    "address": {
                        "addressCountry": "EG",
                        "addressLocality": "Giza",
                    }
                },
            ]
        )
    )

    assert result.location == (
        "Cairo, Egypt; Giza, Egypt"
    )


def test_html_description_priority():

    result = map_job(
        extra="""
        <div data-jb-field="description">
            <p>HTML description.</p>
            <script>ignored()</script>
        </div>
        """
    )

    assert result.description == "HTML description."


def test_json_description_fallback():

    result = map_job()

    assert result.description == "Build data pipelines."


def test_requirements_not_required_skills():

    result = map_job(
        extra="""
        <div data-jb-field="skills">
            Python required. Spark preferred.
        </div>
        """
    )

    assert "Spark preferred" in result.requirements
    assert result.required_skills is None


def test_multiple_employment_types():

    result = map_job(
        make_posting(
            employmentType=[
                "FULL_TIME",
                "CONTRACTOR",
                "FULL_TIME",
            ]
        )
    )

    assert result.employment_types == [
        "full_time",
        "contract",
    ]


def test_internship_employment_type():

    result = map_job(
        make_posting(employmentType="INTERN")
    )

    assert result.opportunity_type == "internship"


def test_internship_title():

    result = map_job(
        make_posting(title="Data Engineering Intern")
    )

    assert result.opportunity_type == "internship"


def test_remote_work_mode():

    result = map_job(
        make_posting(jobLocationType="TELECOMMUTE")
    )

    assert result.work_modes == ["remote"]


def test_missing_work_mode():

    assert map_job().work_modes is None


def test_experience_months():

    result = map_job(
        make_posting(
            experienceRequirements={
                "monthsOfExperience": 18,
            }
        )
    )

    assert result.experience_years_min == Decimal("1.5")
    assert result.experience_years_max is None


def test_experience_range():

    result = map_job(
        extra="""
        <div data-automation-id="data_Years_of_experience">
            1–3 years
        </div>
        """
    )

    assert result.experience_years_min == Decimal("1")
    assert result.experience_years_max == Decimal("3")


def test_experience_minimum():

    result = map_job(
        extra="""
        <div data-automation-id="data_Years_of_experience">
            2+ years
        </div>
        """
    )

    assert result.experience_years_min == Decimal("2")
    assert result.experience_years_max is None


def test_career_level():

    result = map_job(
        extra="""
        <div data-automation-id="data_Career_level">
            Mid career
        </div>
        """
    )

    assert result.experience_level == "mid_level"
    assert result.experience_level_raw == "Mid career"


def test_education_priority():

    result = map_job(
        make_posting(
            educationRequirements={
                "credentialCategory": "Bachelor"
            }
        ),
        extra="""
        <div data-automation-id="data_Degree">
            Bachelor's degree
        </div>
        """
    )

    assert result.education_level == "Bachelor's degree"


def test_salary_range():

    result = map_job(
        make_posting(
            baseSalary={
                "currency": "EGP",
                "value": {
                    "minValue": 10000,
                    "maxValue": 15000,
                    "unitText": "MONTH",
                },
            }
        )
    )

    assert result.salary_min == Decimal("10000")
    assert result.salary_max == Decimal("15000")
    assert result.currency == "EGP"
    assert result.salary_period == "monthly"


def test_fixed_salary():

    result = map_job(
        make_posting(
            baseSalary={
                "currency": "USD",
                "value": {
                    "value": 20,
                    "unitText": "HOUR",
                },
            }
        )
    )

    assert result.salary_min == Decimal("20")
    assert result.salary_max == Decimal("20")
    assert result.salary_period == "hourly"


@pytest.mark.parametrize(
    "salary",
    [
        None,
        {"currency": "INVALID", "value": {"value": 10}},
        {"currency": "EGP", "value": {"value": -10}},
        {"currency": "EGP", "value": {"value": "NaN"}},
        {"currency": "EGP", "value": {"value": True}},
        {
            "currency": "EGP",
            "value": {
                "minValue": 20000,
                "maxValue": 10000,
            },
        },
    ],
)
def test_invalid_salary(salary):

    result = map_job(
        make_posting(baseSalary=salary)
    )

    assert result.salary_min is None
    assert result.salary_max is None
    assert result.currency is None

def test_date_only_precision():

    result = map_job()

    assert result.published_at is None
    assert result.published_at_raw == "2026-11-20"
    assert result.published_at_precision == "date_only"
    assert result.deadline_precision == "date_only"


def test_timezone_aware_date():

    result = map_job(
        make_posting(
            datePosted="2026-11-20T12:00:00+02:00"
        )
    )

    assert result.published_at == datetime(
        2026, 11, 20, 10, tzinfo=timezone.utc
    )

    assert result.published_at_precision == "exact"


def test_active_application():

    result = map_job(
        extra='<a id="applyLink_1">Easy Apply</a>'
    )

    assert result.status == "active"


def test_expired_deadline():

    result = map_job(
        make_posting(validThrough="2026-11-01"),
        extra='<a id="applyLink_1">Easy Apply</a>',
    )

    assert result.status == "expired"


def test_explicit_closed():

    result = map_job(
        extra='<a id="applyLink_1">Job closed</a>'
    )

    assert result.status == "closed"


def test_disabled_application():

    result = map_job(
        extra="""
        <button id="applyLink_1" disabled>
            Easy Apply
        </button>
        """
    )

    assert result.status == "unknown"


def test_missing_application():

    assert map_job().status == "unknown"


def test_external_application_not_closed():

    result = map_job(
        make_posting(directApply=False),
        extra='<a id="applyLink_1">Apply Now</a>',
    )

    assert result.status == "active"
    assert result.raw_payload["direct_apply"] is False


def test_listing_metadata():

    result = map_job(
        listing={
            "is_aggregated": True,
            "is_external": False,
        }
    )

    assert result.raw_payload["is_aggregated"] is True
    assert result.raw_payload["is_external"] is False


def test_raw_payload_minimization():

    result = map_job(
        make_posting(
            unexpected_field="Not needed"
        )
    )

    assert "unexpected_field" not in result.raw_payload
    assert "description" not in result.raw_payload
    assert "hiringOrganization" not in result.raw_payload

def test_html_entities_normalized():

    result = map_job(
        make_posting(
            title="IT &amp; AI Solutions Specialist",
            hiringOrganization={
                "name": "Research &amp; Development"
            },
        )
    )

    assert result.title == "IT & AI Solutions Specialist"
    assert result.organization == "Research & Development"


@pytest.mark.parametrize(
    "career_level",
    ["Fresh graduate", "Fresh graduates"],
)
def test_fresh_graduate_career_level(career_level):

    result = map_job(
        extra=f"""
        <div data-automation-id="data_Career_level">
            {career_level}
        </div>
        """
    )

    assert result.experience_level == "entry_level"
    assert result.experience_level_raw == career_level