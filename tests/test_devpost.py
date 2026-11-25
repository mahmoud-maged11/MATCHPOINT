import json

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

from scrapers.sources.devpost import DevpostScraper

from scrapers.sources.devpost_mapper import (
    DevpostExcludedOpportunity,
    map_devpost_opportunity,
    validate_source_id,
    validate_source_url,
    extract_event,
    extract_deadline,
    extract_prize,
)

from bs4 import BeautifulSoup


OBSERVED = datetime(
    2026, 11, 25,
    tzinfo=timezone.utc
)


@pytest.fixture
def record():

    return {
        "id": 12345,
        "title": "Synthetic AI Hackathon",
        "organization_name": "Example Organization",
        "url": "https://synthetic.devpost.com/",
        "open_state": "open",
        "displayed_location": {
            "icon": "globe",
            "location": "Online",
        },
        "invite_only": False,
        "themes": [
            {"id": 1, "name": "AI"},
            {"id": 2, "name": "Python"},
            {"id": 3, "name": "ai"},
        ],
        "submission_period_dates":
            "Nov 20 - Dec 04, 2026",
        "time_left_to_submission":
            "9 days left",
        "prize_amount":
            '$<span data-currency-value>10,000</span>',
        "registrations_count": 100,
        "prizes_counts": {
            "cash": 1,
            "other": 0,
        },
    }


@pytest.fixture
def detail_html():

    event = {
        "@context": "https://schema.org",
        "@type": "Event",
        "startDate": "2026-11-20T12:00:00-05:00",
        "endDate": "2026-12-04T17:00:00-05:00",
        "organizer": {
            "name": "Fallback Organization"
        },
    }

    return f"""
    <html>
      <head>
        <link rel="canonical"
              href="https://synthetic.devpost.com/">
        <script type="application/ld+json">
          {json.dumps(event)}
        </script>
      </head>
      <body>

        <article id="challenge-description">
          Build an innovative AI application.
        </article>

        <article id="challenge-requirements">
          Submit a working application.
        </article>

        <ul id="eligibility-list">
          <li>Above legal age of majority</li>
          <li>Specific countries excluded</li>
        </ul>

        <h3 id="eligibility-countries-modal-title">
          Specific countries excluded
        </h3>

        <ul id="eligibility-countries-modal-list">
          <li>Cuba</li>
          <li>Iran</li>
        </ul>

        <a href="/register">Join hackathon</a>
        <a href="/rules">Rules</a>

      </body>
    </html>
    """


def mapped(record, detail_html):

    return map_devpost_opportunity(
        record,
        detail_html,
        observed_at=OBSERVED
    )


# ==========================
# Identity and URL validation
# ==========================

@pytest.mark.parametrize(
    "value",
    [None, True, False, 0, -1, "123", 1.5]
)
def test_invalid_source_id(value):

    with pytest.raises(ValueError):
        validate_source_id(value)


def test_valid_source_id():

    assert validate_source_id(123) == "123"


@pytest.mark.parametrize(
    "url",
    [
        None,
        "http://test.devpost.com/",
        "https://devpost.com/",
        "https://example.com/",
        "https://test.devpost.com.evil.com/",
        "https://test.devpost.com/rules",
        "https://test.devpost.com/?x=1",
        "https://test.devpost.com/#section",
        "https://user@test.devpost.com/",
        "https://test.devpost.com:443/",
    ]
)
def test_invalid_source_url(url):

    with pytest.raises(ValueError):
        validate_source_url(url)


def test_valid_source_url():

    assert validate_source_url(
        "https://test.devpost.com"
    ) == "https://test.devpost.com/"


# ==========================
# Mapper
# ==========================

def test_basic_mapping(record, detail_html):

    result = mapped(record, detail_html)

    assert result.source_name == "devpost"
    assert result.source_opportunity_id == "12345"
    assert result.title == record["title"]
    assert result.organization == "Example Organization"
    assert result.opportunity_type == "hackathon"
    assert result.location == "Online"
    assert result.work_modes == ["remote"]
    assert result.status == "active"
    assert result.source_status_raw == "open"


def test_description_and_requirements(
    record,
    detail_html
):

    result = mapped(record, detail_html)

    assert result.description == (
        "Build an innovative AI application."
    )

    assert "Submit a working application" in (
        result.requirements
    )

    assert "Eligibility:" in result.requirements


def test_categories_deduplicated(
    record,
    detail_html
):

    result = mapped(record, detail_html)

    assert result.categories == ["AI", "Python"]


def test_prize_is_not_salary(
    record,
    detail_html
):

    result = mapped(record, detail_html)

    assert result.salary_min is None
    assert result.salary_max is None
    assert result.currency is None

    assert result.raw_payload[
        "prize_amount_raw"
    ] == "$10,000"


def test_exact_deadline(record, detail_html):

    result = mapped(record, detail_html)

    assert result.deadline == datetime(
        2026, 12, 4, 22, 0,
        tzinfo=timezone.utc
    )

    assert result.deadline_precision == "exact"

    assert result.raw_payload[
        "deadline_kind"
    ] == "submission"

    assert result.raw_payload[
        "registration_deadline"
    ] is None


def test_date_only_fallback(
    record,
    detail_html
):

    detail_html = detail_html.replace(
        '"endDate": "2026-12-04T17:00:00-05:00"',
        '"unused": null'
    )

    result = mapped(record, detail_html)

    assert result.deadline is None
    assert result.deadline_raw == "2026-12-04"
    assert result.deadline_precision == "date_only"


def test_expired_deadline(
    record,
    detail_html
):

    detail_html = detail_html.replace(
        "2026-12-04T17:00:00-05:00",
        "2026-11-01T17:00:00-05:00"
    )

    with pytest.raises(
        DevpostExcludedOpportunity
    ):
        mapped(record, detail_html)


def test_upcoming_status(
    record,
    detail_html
):

    record["open_state"] = "upcoming"

    result = mapped(record, detail_html)

    assert result.status == "unknown"
    assert result.source_status_raw == "upcoming"


@pytest.mark.parametrize(
    "status",
    ["closed", "ended", None, "unknown"]
)
def test_excluded_status(
    record,
    detail_html,
    status
):

    record["open_state"] = status

    with pytest.raises(
        DevpostExcludedOpportunity
    ):
        mapped(record, detail_html)


@pytest.mark.parametrize(
    "invite_only",
    [True, None, "false", 0]
)
def test_invite_only_excluded(
    record,
    detail_html,
    invite_only
):

    record["invite_only"] = invite_only

    with pytest.raises(
        DevpostExcludedOpportunity
    ):
        mapped(record, detail_html)


@pytest.mark.parametrize(
    "location",
    ["United States", "Cairo", "Hybrid", None]
)
def test_non_online_excluded(
    record,
    detail_html,
    location
):

    record["displayed_location"][
        "location"
    ] = location

    with pytest.raises(
        DevpostExcludedOpportunity
    ):
        mapped(record, detail_html)


def test_egypt_excluded(
    record,
    detail_html
):

    detail_html = detail_html.replace(
        "<li>Cuba</li>",
        "<li>Egypt</li>"
    )

    with pytest.raises(
        DevpostExcludedOpportunity
    ):
        mapped(record, detail_html)


def test_eligibility_remains_unverified(
    record,
    detail_html
):

    result = mapped(record, detail_html)

    assert result.raw_payload[
        "egypt_eligibility"
    ] == "unverified"

    assert result.raw_payload[
        "excluded_countries"
    ] == ["Cuba", "Iran"]


def test_action_links(
    record,
    detail_html
):

    result = mapped(record, detail_html)

    assert result.raw_payload[
        "registration_url"
    ] == "https://synthetic.devpost.com/register"

    assert result.raw_payload[
        "rules_url"
    ] == "https://synthetic.devpost.com/rules"


def test_external_action_link_ignored(
    record,
    detail_html
):

    detail_html = detail_html.replace(
        'href="/register"',
        'href="https://example.com/register"'
    )

    result = mapped(record, detail_html)

    assert result.raw_payload[
        "registration_url"
    ] is None


def test_canonical_mismatch(
    record,
    detail_html
):

    detail_html = detail_html.replace(
        "https://synthetic.devpost.com/",
        "https://different.devpost.com/"
    )

    with pytest.raises(ValueError):
        mapped(record, detail_html)


def test_organization_fallback(
    record,
    detail_html
):

    record["organization_name"] = None

    result = mapped(record, detail_html)

    assert result.organization == (
        "Fallback Organization"
    )


def test_missing_title(record, detail_html):

    record["title"] = " "

    with pytest.raises(ValueError):
        mapped(record, detail_html)


def test_missing_description(
    record,
    detail_html
):

    detail_html = detail_html.replace(
        "Build an innovative AI application.",
        ""
    )

    with pytest.raises(ValueError):
        mapped(record, detail_html)


def test_naive_observation_rejected(
    record,
    detail_html
):

    with pytest.raises(ValueError):

        map_devpost_opportunity(
            record,
            detail_html,
            observed_at=datetime(2026, 11, 25)
        )


def test_invalid_json_ld():

    soup = BeautifulSoup(
        '<script type="application/ld+json">'
        'invalid JSON</script>',
        "html.parser"
    )

    assert extract_event(soup) == {}


def test_missing_deadline():

    assert extract_deadline({}, {}) is None


def test_missing_prize():

    assert extract_prize({}) is None


# ==========================
# Collector
# ==========================

@pytest.fixture
def scraper():

    instance = DevpostScraper(
        max_jobs=4,
        max_pages=2
    )

    instance.reset_stats()

    instance.record_invalid = Mock()

    yield instance

    instance.client.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_jobs": 0},
        {"max_jobs": -1},
        {"max_jobs": True},
        {"max_pages": 0},
        {"max_pages": -1},
        {"max_pages": False},
    ]
)
def test_invalid_limits(kwargs):

    with pytest.raises(ValueError):
        DevpostScraper(**kwargs)


def test_listing_parameters(
    scraper,
    record
):

    response = Mock()

    response.json.return_value = {
        "hackathons": [record],
        "meta": {
            "total_count": 20,
            "per_page": 9,
        },
    }

    scraper.fetch = Mock(
        return_value=response
    )

    records, total, per_page = (
        scraper.fetch_listing("open", 2)
    )

    assert records == [record]
    assert total == 20
    assert per_page == 9

    scraper.fetch.assert_called_once_with(
        "https://devpost.com/api/hackathons",
        params={
            "status[]": "open",
            "location[]": "online",
            "page": 2,
        }
    )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"hackathons": []},
        {
            "hackathons": [],
            "meta": {
                "total_count": -1,
                "per_page": 9,
            }
        },
        {
            "hackathons": [],
            "meta": {
                "total_count": 10,
                "per_page": 0,
            }
        },
    ]
)
def test_invalid_listing_payload(
    scraper,
    payload
):

    response = Mock()
    response.json.return_value = payload

    scraper.fetch = Mock(
        return_value=response
    )

    with pytest.raises(ValueError):
        scraper.fetch_listing("open", 1)


def test_duplicate_skips_detail(
    scraper,
    record
):

    scraper.fetch = Mock()

    result = scraper.collect_record(
        record,
        seen_ids={"12345"},
        seen_urls=set(),
        expected_status="open"
    )

    assert result is None
    assert scraper.stats["duplicates"] == 1

    scraper.fetch.assert_not_called()


def test_wrong_status_skips_detail(
    scraper,
    record
):

    scraper.fetch = Mock()

    result = scraper.collect_record(
        record,
        seen_ids=set(),
        seen_urls=set(),
        expected_status="upcoming"
    )

    assert result is None
    assert scraper.stats["excluded"] == 1

    scraper.fetch.assert_not_called()


def test_invalid_record_logged(scraper):

    result = scraper.collect_record(
        {"id": None},
        seen_ids=set(),
        seen_urls=set(),
        expected_status="open"
    )

    assert result is None
    assert scraper.stats["invalid"] == 1

    scraper.record_invalid.assert_called_once()


@pytest.mark.parametrize(
    "status",
    [404, 410]
)
def test_missing_detail(
    scraper,
    record,
    status
):

    response = requests.Response()
    response.status_code = status

    scraper.fetch = Mock(
        side_effect=requests.HTTPError(
            response=response
        )
    )

    result = scraper.collect_record(
        record,
        seen_ids=set(),
        seen_urls=set(),
        expected_status="open"
    )

    assert result is None
    assert scraper.stats["details_missing"] == 1


@pytest.mark.parametrize(
    "status",
    [403, 429, 500]
)
def test_http_failure_propagates(
    scraper,
    record,
    status
):

    response = requests.Response()
    response.status_code = status

    scraper.fetch = Mock(
        side_effect=requests.HTTPError(
            response=response
        )
    )

    with pytest.raises(requests.HTTPError):

        scraper.collect_record(
            record,
            seen_ids=set(),
            seen_urls=set(),
            expected_status="open"
        )


def test_robots_disallowed(scraper):

    robots = Mock()
    robots.can_fetch.return_value = False

    scraper.get_robots = Mock(
        return_value=robots
    )

    scraper.request = Mock()

    with pytest.raises(PermissionError):

        scraper.fetch(
            "https://synthetic.devpost.com/"
        )

    scraper.request.assert_not_called()


def test_robots_cached(scraper):

    response = Mock()

    response.text = (
        "User-agent: *\nDisallow:"
    )

    scraper.request = Mock(
        return_value=response
    )

    first = scraper.get_robots(
        "synthetic.devpost.com"
    )

    second = scraper.get_robots(
        "synthetic.devpost.com"
    )

    assert first is second

    scraper.request.assert_called_once()


def test_redirect_rejected(scraper):

    response = Mock()
    response.status_code = 302

    scraper.client.session.get = Mock(
        return_value=response
    )

    scraper.client.rate_limiter.wait = Mock()

    with pytest.raises(RuntimeError):

        scraper.request(
            "https://synthetic.devpost.com/"
        )

    assert scraper.client.session.get.call_args.kwargs[
        "allow_redirects"
    ] is False


def test_unexpected_host(scraper):

    with pytest.raises(ValueError):

        scraper.fetch(
            "https://example.com/"
        )


def test_round_robin_and_max_jobs(scraper):

    scraper.fetch_listing = Mock(
        side_effect=lambda status, page: (
            [
                {"id": f"{status}-{page}-1"},
                {"id": f"{status}-{page}-2"},
            ],
            4,
            2
        )
    )

    scraper.collect_record = Mock(
        side_effect=lambda record, **kwargs: record
    )

    results = scraper.scrape()

    assert len(results) == 4

    assert [item["id"] for item in results] == [
        "open-1-1",
        "upcoming-1-1",
        "open-1-2",
        "upcoming-1-2",
    ]


def test_max_pages_enforced(scraper):

    scraper.fetch_listing = Mock(
        return_value=(
            [{"id": 1}],
            1000,
            1
        )
    )

    scraper.collect_record = Mock(
        return_value=None
    )

    assert scraper.scrape() == []

    assert scraper.fetch_listing.call_count == 4


def test_empty_listings_stop(scraper):

    scraper.fetch_listing = Mock(
        return_value=([], 0, 9)
    )

    scraper.collect_record = Mock()

    assert scraper.scrape() == []

    assert scraper.fetch_listing.call_count == 2

    scraper.collect_record.assert_not_called()

# Additional country eligibility validation

@pytest.mark.parametrize(
    "countries, accepted",
    [
        (["Egypt", "Germany"], True),
        (["Germany", "France"], False),
        ([], False),
    ]
)
def test_country_allowlist(
    record,
    detail_html,
    countries,
    accepted
):

    detail_html = detail_html.replace(
        "Specific countries excluded",
        "Only specific countries/territories included"
    )

    country_html = "".join(
        f"<li>{country}</li>"
        for country in countries
    )

    detail_html = detail_html.replace(
        "<li>Cuba</li>",
        country_html
    ).replace(
        "<li>Iran</li>",
        ""
    )

    if accepted:

        result = mapped(record, detail_html)

        assert result.raw_payload[
            "included_countries"
        ] == countries

        assert result.raw_payload[
            "egypt_eligibility"
        ] == "unverified"

    else:

        with pytest.raises(
            DevpostExcludedOpportunity
        ):
            mapped(record, detail_html)


def test_missing_country_blocklist(
    record,
    detail_html
):

    detail_html = detail_html.replace(
        "<li>Cuba</li>",
        ""
    ).replace(
        "<li>Iran</li>",
        ""
    )

    with pytest.raises(
        DevpostExcludedOpportunity
    ):
        mapped(record, detail_html)
