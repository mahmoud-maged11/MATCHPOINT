
from unittest.mock import Mock

import pytest
import requests

from scrapers.collection_result import StopReason
from scrapers.sources.wuzzuf_api import WuzzufAPIScraper

from test_wuzzuf_api import make_job


def make_scraper(jobs):

    scraper = WuzzufAPIScraper(
        max_jobs=None,
        max_pages=None,
        page_size=20,
    )

    scraper.fetch_page = Mock(
        return_value=jobs
    )

    return scraper


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("DNS failure"),
        requests.Timeout("Company timeout"),
    ],
)
def test_temporary_failure_preserves_jobs(error):

    scraper = make_scraper([
        make_job("1"),
        make_job("2"),
        make_job("3"),
    ])

    scraper.fetch_company_name = Mock(
        side_effect=error
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 3
    assert result.rejected_count == 0

    assert not result.scope_completed
    assert result.stop_reason == StopReason.SOURCE_ERROR

    assert scraper.fetch_company_name.call_count == 1

    assert scraper.stats[
        "company_enrichment_deferred"
    ] == 3

    for opportunity in result.opportunities:

        assert opportunity.organization is None

        assert opportunity.raw_payload[
            "company_id"
        ] == "123"

        assert opportunity.raw_payload[
            "_matchpoint_company_enrichment"
        ] == "temporary_failure"


@pytest.mark.parametrize(
    "status_code",
    [401, 403, 500, 502, 503, 504],
)
def test_deferred_http_failures(status_code):

    scraper = make_scraper([
        make_job("1"),
        make_job("2"),
    ])

    response = requests.Response()
    response.status_code = status_code

    scraper.fetch_company_name = Mock(
        side_effect=requests.HTTPError(
            response=response
        )
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 2
    assert result.rejected_count == 0

    assert not result.scope_completed

    assert scraper.fetch_company_name.call_count == 1

    expected = (
        "access_denied"
        if status_code in {401, 403}
        else "temporary_failure"
    )

    for opportunity in result.opportunities:

        assert opportunity.raw_payload[
            "_matchpoint_company_enrichment"
        ] == expected


def test_confidential_company_not_requested():

    job = make_job("1")

    job["attributes"]["hideCompany"] = True

    scraper = make_scraper([job])

    scraper.fetch_company_name = Mock()

    result = scraper.run_with_result()

    assert result.accepted_count == 1
    assert result.source_exhausted

    scraper.fetch_company_name.assert_not_called()

    opportunity = result.opportunities[0]

    assert opportunity.organization is None

    assert "company_id" not in opportunity.raw_payload

    assert (
        "_matchpoint_company_enrichment"
        not in opportunity.raw_payload
    )

    assert scraper.stats[
        "confidential_companies"
    ] == 1


def test_visible_company_identity_retained():

    scraper = make_scraper([
        make_job("1")
    ])

    scraper.fetch_company_name = Mock(
        return_value="Test Company"
    )

    result = scraper.run_with_result()

    opportunity = result.opportunities[0]

    assert opportunity.organization == "Test Company"

    assert opportunity.raw_payload[
        "company_id"
    ] == "123"

    assert result.source_exhausted


def test_rate_limit_stops_collection():

    first = make_job("1")
    second = make_job("2")

    second["relationships"]["company"]["data"][
        "id"
    ] = "456"

    scraper = make_scraper([
        first, second
    ])

    response = requests.Response()
    response.status_code = 429

    scraper.fetch_company_name = Mock(
        side_effect=[
            "Test Company",
            requests.HTTPError(response=response),
        ]
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 1
    assert not result.scope_completed

    assert result.stop_reason == StopReason.SOURCE_ERROR


def test_job_api_failure_remains_partial():

    scraper = WuzzufAPIScraper(
        max_jobs=None,
        max_pages=None,
        page_size=1,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            [make_job("1")],
            requests.ConnectionError("DNS failure"),
        ]
    )

    scraper.fetch_company_name = Mock(
        return_value="Test Company"
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 1
    assert not result.scope_completed
    assert result.stop_reason == StopReason.SOURCE_ERROR
