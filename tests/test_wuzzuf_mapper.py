import pytest

from scrapers.sources.wuzzuf_mapper import WuzzufMapper


@pytest.fixture
def job():

    return {
        "id": "api-test-001",
        "attributes": {
            "slug": "test001-data-engineer",
            "uri": "jobs/p/test001-data-engineer",
            "title": "Data Engineer",
            "jobType": "job",
            "status": "active",
            "hideSalary": False,
            "hideCompany": False,

            "description": "<p>Build pipelines</p>",
            "requirements": "<p>Python and SQL</p>",

            "location": {
                "city": {"name": "Cairo"},
                "country": {
                    "name": "Egypt",
                    "code": "EG"
                }
            },

            "workplaceArrangement": {
                "displayedName": "Remote"
            },

            "workTypes": [
                {"name": "full_time"}
            ],

            "careerLevel": {
                "name": "Entry Level"
            },

            "workExperienceYears": {
                "min": 0,
                "max": 2
            },

            "keywords": [
                {"name": "Python"},
                {"name": "SQL"}
            ],

            "salary": {
                "min": 10000,
                "max": 15000,
                "currency": {"code": "EGP"}
            },

            "postedAt": "11/25/2026 10:00:00"
        }
    }


def test_source_identity(job):

    result = WuzzufMapper().map_job(job)

    assert result.source_name == "wuzzuf"
    assert result.source_opportunity_id == "test001"
    assert result.raw_payload["api_id"] == "api-test-001"


def test_title_and_company(job):

    result = WuzzufMapper().map_job(
        job, "Test Company"
    )

    assert result.title == "Data Engineer"
    assert result.organization == "Test Company"


def test_html_cleaning(job):

    result = WuzzufMapper().map_job(job)

    assert result.description == "Build pipelines"
    assert result.requirements == "Python and SQL"


def test_location(job):

    result = WuzzufMapper().map_job(job)

    assert result.location == "Cairo, Egypt"


def test_work_information(job):

    result = WuzzufMapper().map_job(job)

    assert result.work_modes == ["remote"]
    assert result.employment_types == ["full_time"]


def test_experience(job):

    result = WuzzufMapper().map_job(job)

    assert result.experience_level == "entry_level"
    assert result.experience_years_min == 0
    assert result.experience_years_max == 2


def test_skills(job):

    result = WuzzufMapper().map_job(job)

    assert result.required_skills == ["Python", "SQL"]


def test_salary(job):

    result = WuzzufMapper().map_job(job)

    assert result.salary_min == 10000
    assert result.salary_max == 15000
    assert result.currency == "EGP"


def test_hidden_salary(job):

    job["attributes"]["hideSalary"] = True

    result = WuzzufMapper().map_job(job)

    assert result.salary_min is None
    assert result.salary_max is None
    assert result.currency is None
    assert "salary" not in result.raw_payload["attributes"]


def test_hidden_company(job):

    job["attributes"]["hideCompany"] = True

    result = WuzzufMapper().map_job(job, "Hidden")

    assert result.organization is None


def test_unknown_timezone(job):

    result = WuzzufMapper().map_job(job)

    assert result.published_at is None
    assert result.published_at_raw == "11/25/2026 10:00:00"
    assert result.published_at_precision == "unknown"


def test_internship(job):

    job["attributes"]["jobType"] = "internship"

    job["attributes"]["workTypes"] = [
        {"name": "internship"}
    ]

    result = WuzzufMapper().map_job(job)

    assert result.opportunity_type == "internship"
    assert result.employment_types is None


def test_missing_slug(job):

    del job["attributes"]["slug"]

    with pytest.raises(ValueError):
        WuzzufMapper().map_job(job)



def test_salary_period(job):

    job["attributes"]["salary"]["period"] = {
        "name": "Per Month"
    }

    result = WuzzufMapper().map_job(job)

    assert result.salary_period == "monthly"


def test_hidden_salary_period(job):

    job["attributes"]["salary"]["period"] = {
        "name": "Per Month"
    }

    job["attributes"]["hideSalary"] = True

    result = WuzzufMapper().map_job(job)

    assert result.salary_period is None
    assert "salary" not in result.raw_payload["attributes"]


def test_whitespace_company(job):

    result = WuzzufMapper().map_job(
        job, "   "
    )

    assert result.organization is None


def test_external_source_url(job):

    job["attributes"]["uri"] = (
        "https://example.com/jobs/p/test001-data-engineer"
    )

    with pytest.raises(ValueError):
        WuzzufMapper().map_job(job)


def test_internal_fields_excluded(job):

    job["attributes"]["insights"] = {
        "internal": True
    }

    job["attributes"]["internalField"] = "private"

    result = WuzzufMapper().map_job(job)

    raw = result.raw_payload["attributes"]

    assert "insights" not in raw
    assert "internalField" not in raw


def test_source_status_preserved(job):

    result = WuzzufMapper().map_job(job)

    assert result.source_status_raw == "active"


def test_internship_url(job):

    job["attributes"]["jobType"] = "internship"

    job["attributes"]["uri"] = (
        "internship/test001-data-engineer"
    )

    result = WuzzufMapper().map_job(job)

    assert result.opportunity_type == "internship"

    assert str(result.source_url) == (
        "https://wuzzuf.net/internship/test001-data-engineer"
    )