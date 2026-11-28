from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
import requests

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from scrapers.sources.wuzzuf import WuzzufScraper

from scrapers.sources.wuzzuf_api import WuzzufAPIScraper

from test_wuzzuf_api import make_job


def make_scraper(pages, **kwargs):

    settings = {
        "max_jobs": 10,
        "page_size": 2,
        "max_pages": 5,
    }

    settings.update(kwargs)

    scraper = WuzzufAPIScraper(**settings)

    scraper.client.close = Mock()

    scraper.fetch_page = Mock(
        side_effect=pages,
    )

    scraper.fetch_company_name = Mock(
        return_value="Test Company",
    )

    return scraper


def test_requested_job_limit():

    scraper = make_scraper(
        [[make_job("1"), make_job("2")]],
        max_jobs=2,
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.COMPLETED
    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert result.accepted_count == 2
    assert not result.source_exhausted

    assert scraper.fetch_page.call_count == 1


def test_requested_page_limit():

    scraper = make_scraper(
        [[make_job("1"), make_job("2")]],
        max_pages=1,
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert result.accepted_count == 2
    assert not result.source_exhausted


def test_empty_source():

    scraper = make_scraper([[]])

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 0
    assert result.rejected_count == 0


def test_source_exhausted_after_full_page():

    scraper = make_scraper([
        [make_job("1"), make_job("2")],
        [],
    ])

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 2

    assert scraper.fetch_page.call_count == 2


def test_short_page():

    scraper = make_scraper([
        [make_job("1")],
    ])

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 1


def test_duplicate_page():

    scraper = make_scraper([
        [make_job("1"), make_job("2")],
        [make_job("1"), make_job("2")],
    ])

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 2
    assert not result.source_exhausted

    assert scraper.fetch_page.call_count == 2


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("Connection failed"),
        requests.Timeout("Request timed out"),
        requests.HTTPError("HTTP request failed"),
    ],
)
def test_initial_request_failure(error):

    scraper = make_scraper([error])

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 0
    assert result.rejected_count == 0

    scraper.client.close.assert_called_once()


def test_request_failure_preserves_previous_page():

    scraper = make_scraper([
        [make_job("1"), make_job("2")],
        requests.ConnectionError("Connection lost"),
    ])

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 2
    assert result.rejected_count == 0

    assert {
        item.source_opportunity_id
        for item in result.opportunities
    } == {"1", "2"}


def test_initial_parsing_failure():

    scraper = make_scraper([
        ValueError("Invalid API response"),
    ])

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.returned_count == 0


def test_parsing_failure_preserves_previous_page():

    scraper = make_scraper([
        [make_job("1"), make_job("2")],
        ValueError("Invalid API response"),
    ])

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 2
    assert result.rejected_count == 0



def test_company_request_failure():

    from unittest.mock import Mock

    import requests

    from scrapers.collection_result import StopReason
    from scrapers.sources.wuzzuf_api import WuzzufAPIScraper
    from test_wuzzuf_api import make_job

    first = make_job("1")
    second = make_job("2")
    third = make_job("3")

    first["relationships"]["company"]["data"]["id"] = "456"
    second["relationships"]["company"]["data"]["id"] = "123"
    third["relationships"]["company"]["data"]["id"] = "789"

    scraper = WuzzufAPIScraper(
        max_jobs=None,
        max_pages=None,
        page_size=2,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            [first, second],
            [third],
        ]
    )

    def company_lookup(company_id):

        if company_id == "123":
            raise requests.ConnectionError(
                "Temporary DNS failure"
            )

        return "Company " + company_id

    scraper.fetch_company_name = Mock(
        side_effect=company_lookup
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 3
    assert result.rejected_count == 0

    assert not result.scope_completed
    assert result.stop_reason == StopReason.SOURCE_ERROR

    assert scraper.fetch_page.call_count == 2
    assert scraper.fetch_company_name.call_count == 3

    assert scraper.stats["company_request_failures"] == 1
    assert scraper.stats["company_enrichment_deferred"] == 1

    first_result, deferred, third_result = result.opportunities

    assert first_result.organization == "Company 456"
    assert third_result.organization == "Company 789"

    assert deferred.organization is None
    assert deferred.raw_payload["company_id"] == "123"

    assert deferred.raw_payload[
        "_matchpoint_company_enrichment"
    ] == "temporary_failure"

    for opportunity in (first_result, third_result):

        assert (
            "_matchpoint_company_enrichment"
            not in opportunity.raw_payload
        )



def test_company_parsing_failure():

    scraper = make_scraper([
        [make_job("1"), make_job("2")],
    ])

    scraper.fetch_company_name.side_effect = [
        "Test Company",
        ValueError("Invalid company response"),
    ]

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0


def test_invalid_record_does_not_mean_collection_failure():

    job = make_job("1")

    del job["attributes"]["title"]

    scraper = make_scraper([[job]])

    run_id = uuid4()

    result = scraper.run_with_result(
        run_id=run_id,
    )

    assert result.scope_completed
    assert result.accepted_count == 0
    assert result.rejected_count == 1
    assert result.returned_count == 1

    assert result.run_id == run_id

    assert result.invalid_records[0].run_id == str(run_id)


def test_filtered_records_are_not_rejections():

    job = make_job("1")

    job["attributes"]["status"] = "expired"

    scraper = make_scraper([[job]])

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 0
    assert result.rejected_count == 0


def test_html_input_completed():

    path = (
        Path(__file__).parent
        / "fixtures"
        / "wuzzuf_synthetic.html"
    )

    scraper = WuzzufScraper(str(path))

    scraper.client.close = Mock()

    run_id = uuid4()

    result = scraper.run_with_result(
        run_id=run_id,
    )

    assert result.scope_completed
    assert result.stop_reason == StopReason.INPUT_EXHAUSTED
    assert not result.source_exhausted

    assert result.accepted_count == 3
    assert result.rejected_count == 2
    assert result.returned_count == 5

    assert all(
        record.run_id == str(run_id)
        for record in result.invalid_records
    )


@pytest.mark.parametrize(
    "html",
    [
        "",
        "<html><body>Unexpected page</body></html>",
    ],
)
def test_html_without_job_cards(tmp_path, html):

    path = tmp_path / "invalid_wuzzuf.html"

    path.write_text(
        html,
        encoding="utf-8",
    )

    scraper = WuzzufScraper(str(path))

    scraper.client.close = Mock()

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert not result.scope_completed
    assert result.returned_count == 0


def test_unexpected_programming_error_not_swallowed():

    scraper = make_scraper([
        RuntimeError("Unexpected programming error"),
    ])

    with pytest.raises(
        RuntimeError,
        match="Unexpected programming error",
    ):

        scraper.run_with_result()

    assert scraper.last_result.status == CollectionStatus.FAILED

    scraper.client.close.assert_called_once()
