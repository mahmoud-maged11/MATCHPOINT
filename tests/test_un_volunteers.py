from datetime import datetime, timezone
from copy import deepcopy
from unittest.mock import Mock

import pytest
import requests

from scrapers.sources.un_volunteers import (
    UNVolunteersScraper
)

from scrapers.sources.un_volunteers_mapper import (
    map_un_volunteers_opportunity,
    is_target_assignment,
    validate_id,
    UNVExcludedOpportunity
)


OBSERVED = datetime(
    2026, 11, 25,
    tzinfo=timezone.utc
)


def lookup(label, code):

    return {
        "label": label,
        "value": {"code": code}
    }


@pytest.fixture
def listing():

    return {
        "id": 123456,
        "name": "English Training",
        "isOnsite": False,
        "country": lookup("Egypt", "EGY"),
        "publishDate": "2026-11-24T10:00:00Z"
    }


@pytest.fixture
def detail(listing):

    return {
        **deepcopy(listing),
        "doaRequestNo": "123456",
        "hostEntity": {
            "name": "WFP"
        },
        "taskDescription": "Deliver English training.",
        "requiredEducation": lookup(
            "Bachelor's degree",
            "BACH_DEG"
        ),
        "requiredSkillExperience": (
            "Minimum of 3 years of experience."
        ),
        "requiredExperience": 0,
        "unitOfExperience": None,
        "additionalEligibilityCriteria": (
            "Strong communication skills."
        ),
        "languages": [
            {
                "language": lookup(
                    "English", "LAN_ENG"
                ),
                "level": lookup(
                    "Fluent", "FLUENT"
                ),
                "isRequired": True
            }
        ],
        "expertiseAreas": [
            lookup("Education", "AOE_105")
        ],
        "duration": 84,
        "hoursWeek": lookup(
            "1 - 5 hours per week", "1_5"
        ),
        "status": lookup(
            "Recruiting", "DOA_SOURCING"
        ),
        "sourcingEndDate": "2026-12-08T00:00:00",
        "isSourcingActive": True,
        "isReserved": False,
        "isSingleSource": False,
        "canApply": None,
        "volunteersNumber": 6,
        "sdgType": lookup(
            "Zero hunger", "SDG_2"
        )
    }


def test_basic_mapping(listing, detail):

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    assert result.source_name == "un_volunteers"
    assert result.source_opportunity_id == "123456"
    assert result.title == "English Training"
    assert result.organization == "WFP"
    assert result.opportunity_type == "volunteering"
    assert result.location == "Egypt"
    assert result.status == "active"
    assert result.work_modes == ["remote"]

    assert str(result.source_url) == (
        "https://app.unv.org/opportunities/123456"
    )


def test_description(listing, detail):

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    assert result.description == (
        "Deliver English training."
    )


def test_requirements(listing, detail):

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    assert "3 years" in result.requirements
    assert "Strong communication" in result.requirements
    assert "English - Fluent" in result.requirements
    assert result.education_level == "Bachelor's degree"


def test_categories(listing, detail):

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    assert result.categories == ["Education"]


def test_published_date(listing, detail):

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    assert result.published_at is not None
    assert result.published_at_precision == "exact"


def test_deadline_uncertainty(listing, detail):

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    assert result.deadline is None
    assert result.deadline_precision == "unknown"

    assert result.deadline_raw == (
        "2026-12-08T00:00:00"
    )


def test_zero_experience_not_inferred(listing, detail):

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    assert result.experience_years_min is None
    assert result.experience_years_max is None

    assert result.raw_payload[
        "required_experience_raw"
    ] == 0


def test_salary_not_inferred(listing, detail):

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    assert result.salary_min is None
    assert result.salary_max is None
    assert result.currency is None

    assert result.raw_payload[
        "compensation_type"
    ] == "unpaid"


def test_eligibility_unverified(listing, detail):

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    assert result.raw_payload[
        "egypt_eligibility"
    ] == "unverified"


@pytest.mark.parametrize(
    "onsite,country,expected",
    [
        (False, "EGY", True),
        (False, "TUR", True),
        (False, "CMR", True),
        (True, "EGY", True),
        (True, "CMR", False),
        (True, "TUR", False),
        (None, "EGY", False),
        ("false", "EGY", False),
        (True, None, False)
    ]
)
def test_target_filter(onsite, country, expected):

    record = {
        "isOnsite": onsite,
        "country": lookup("Country", country)
    }

    assert is_target_assignment(record) is expected


def test_onsite_egypt(listing, detail):

    listing["isOnsite"] = True
    detail["isOnsite"] = True

    detail["volunteersCategoryDetails"] = {
        "workArrangement": lookup(
            "Full-time", "FULLTIME"
        )
    }

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    assert result.work_modes == ["on_site"]
    assert result.employment_types == ["full_time"]


def test_onsite_outside_egypt(listing, detail):

    listing["isOnsite"] = True
    detail["isOnsite"] = True

    detail["country"] = lookup(
        "Cameroon", "CMR"
    )

    with pytest.raises(UNVExcludedOpportunity):

        map_un_volunteers_opportunity(
            listing, detail, OBSERVED
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("isSourcingActive", False),
        ("isSourcingActive", None),
        ("isReserved", True),
        ("isReserved", None),
        ("isSingleSource", True),
        ("isSingleSource", None),
        ("status", lookup("Closed", "CLOSED"))
    ]
)
def test_excluded_status(listing, detail, field, value):

    detail[field] = value

    with pytest.raises(UNVExcludedOpportunity):

        map_un_volunteers_opportunity(
            listing, detail, OBSERVED
        )


def test_expired_assignment(listing, detail):

    detail["sourcingEndDate"] = (
        "2026-11-20T00:00:00"
    )

    with pytest.raises(UNVExcludedOpportunity):

        map_un_volunteers_opportunity(
            listing, detail, OBSERVED
        )


@pytest.mark.parametrize(
    "deadline",
    [
        None,
        "invalid",
        "2026-11-25T00:00:00",
        "2026-11-24T00:00:00"
    ]
)
def test_uncertain_status(listing, detail, deadline):

    detail["sourcingEndDate"] = deadline

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    assert result.status == "unknown"


@pytest.mark.parametrize(
    "value",
    [None, 0, -1, True, "123", 1.5]
)
def test_invalid_id(value):

    with pytest.raises(ValueError):
        validate_id(value)


def test_id_mismatch(listing, detail):

    detail["id"] = 999

    with pytest.raises(ValueError):

        map_un_volunteers_opportunity(
            listing, detail, OBSERVED
        )


def test_modality_mismatch(listing, detail):

    detail["isOnsite"] = True

    with pytest.raises(ValueError):

        map_un_volunteers_opportunity(
            listing, detail, OBSERVED
        )


@pytest.mark.parametrize(
    "field",
    ["name", "taskDescription"]
)
def test_missing_required_field(listing, detail, field):

    detail[field] = None

    with pytest.raises(ValueError):

        map_un_volunteers_opportunity(
            listing, detail, OBSERVED
        )


def test_private_fields_not_stored(listing, detail):

    detail["hiringManager"] = {
        "email": "private@example.com"
    }

    detail["hostEntityContacts"] = [
        {"email": "contact@example.com"}
    ]

    result = map_un_volunteers_opportunity(
        listing, detail, OBSERVED
    )

    serialized = result.model_dump_json()

    assert "private@example.com" not in serialized
    assert "contact@example.com" not in serialized
    assert "hiringManager" not in serialized


def test_naive_observation_rejected(listing, detail):

    with pytest.raises(ValueError):

        map_un_volunteers_opportunity(
            listing,
            detail,
            datetime(2026, 11, 25)
        )


@pytest.fixture
def scraper():

    instance = UNVolunteersScraper(
        max_jobs=10,
        page_size=10,
        max_pages=3
    )

    yield instance

    instance.client.session.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_jobs": 0},
        {"page_size": 0},
        {"max_pages": -1},
        {"max_jobs": True},
        {"page_size": "10"}
    ]
)
def test_invalid_limits(kwargs):

    with pytest.raises(ValueError):
        UNVolunteersScraper(**kwargs)


def test_listing_payload(scraper, listing):

    scraper.request_json = Mock(
        return_value={
            "result": [listing],
            "total": 1,
            "skip": 0
        }
    )

    records, total = scraper.fetch_listing(0)

    assert records == [listing]
    assert total == 1

    scraper.request_json.assert_called_once_with(
        "POST",
        scraper.SEARCH_URL,
        {
            "filters": [],
            "take": 10,
            "skip": 0
        }
    )


@pytest.mark.parametrize(
    "value",
    [
        {"result": None, "total": 1, "skip": 0},
        {"result": [], "total": -1, "skip": 0},
        {"result": [], "total": True, "skip": 0},
        {"result": [], "total": 1, "skip": 10}
    ]
)
def test_invalid_listing_response(scraper, value):

    scraper.request_json = Mock(
        return_value=value
    )

    with pytest.raises(ValueError):
        scraper.fetch_listing(0)


def test_duplicate_listing(scraper, listing):

    seen = {listing["id"]}

    scraper.fetch_detail = Mock()

    assert scraper.collect_record(
        listing, seen
    ) is None

    assert scraper.stats["duplicates"] == 1

    scraper.fetch_detail.assert_not_called()


def test_excluded_before_detail(scraper, listing):

    listing["isOnsite"] = True

    listing["country"] = lookup(
        "Cameroon", "CMR"
    )

    scraper.fetch_detail = Mock()

    assert scraper.collect_record(
        listing, set()
    ) is None

    scraper.fetch_detail.assert_not_called()

    assert scraper.stats["excluded"] == 1


@pytest.mark.parametrize("status", [404, 410])
def test_missing_detail(scraper, listing, status):

    response = requests.Response()
    response.status_code = status

    scraper.fetch_detail = Mock(
        side_effect=requests.HTTPError(
            response=response
        )
    )

    assert scraper.collect_record(
        listing, set()
    ) is None

    assert scraper.stats["details_missing"] == 1


@pytest.mark.parametrize(
    "status",
    [401, 403, 429, 500]
)
def test_http_failure_propagates(scraper, listing, status):

    response = requests.Response()
    response.status_code = status

    scraper.fetch_detail = Mock(
        side_effect=requests.HTTPError(
            response=response
        )
    )

    with pytest.raises(requests.HTTPError):

        scraper.collect_record(
            listing, set()
        )


def test_empty_collection(scraper):

    scraper.fetch_listing = Mock(
        return_value=([], 0)
    )

    assert scraper.scrape() == []


def test_max_pages(scraper, listing):

    scraper.fetch_listing = Mock(
        return_value=([listing], 100)
    )

    scraper.collect_record = Mock(
        return_value=None
    )

    assert scraper.scrape() == []

    assert scraper.fetch_listing.call_count == 3


def test_max_jobs(scraper, listing):

    scraper.max_jobs = 1

    scraper.fetch_listing = Mock(
        return_value=([listing, listing], 100)
    )

    scraper.collect_record = Mock(
        return_value=Mock()
    )

    assert len(scraper.scrape()) == 1

    assert scraper.collect_record.call_count == 1


def test_automatic_retries_disabled(scraper):

    adapter = scraper.client.session.get_adapter(
        scraper.SEARCH_URL
    )

    assert adapter.max_retries.total == 0