
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from scrapers.sources.devpost import DevpostScraper

from test_devpost import record, detail_html


@pytest.fixture
def collector():

    instance = DevpostScraper(
        max_jobs=10,
        max_pages=2,
    )

    instance.client.close()
    instance.client = Mock()

    yield instance


def configure(collector, record, detail_html):

    records = {}

    for index, status in enumerate(
        ("open", "upcoming"), start=1
    ):

        item = deepcopy(record)

        item["id"] = index
        item["open_state"] = status
        item["url"] = (
            f"https://synthetic-{index}.devpost.com/"
        )

        records[status] = item

    def listing(status, page):

        if page == 1:

            return [records[status]], 1, 1

        return [], 1, 1

    def detail(url):

        response = Mock()

        response.text = detail_html.replace(
            "https://synthetic.devpost.com/",
            url,
        ).replace(
            "2026-12-04",
            "2099-12-04",
        )

        return response

    collector.fetch_listing = Mock(
        side_effect=listing
    )

    collector.fetch = Mock(
        side_effect=detail
    )

    return records


def test_source_exhausted(
    collector, record, detail_html
):

    configure(collector, record, detail_html)

    result = collector.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 2

    assert [
        item.source_status_raw
        for item in result.opportunities
    ] == ["open", "upcoming"]

    assert all(
        report["completed"]
        for report in collector.stats[
            "status_results"
        ].values()
    )


def test_requested_job_limit(
    collector, record, detail_html
):

    configure(collector, record, detail_html)

    collector.max_jobs = 1

    result = collector.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert result.accepted_count == 1
    assert not result.source_exhausted


def test_requested_page_limit(
    collector, record, detail_html
):

    records = configure(
        collector, record, detail_html
    )

    collector.max_pages = 1

    collector.fetch_listing.side_effect = (
        lambda status, page: (
            [records[status]], 10, 1
        )
    )

    result = collector.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert result.accepted_count == 2
    assert collector.fetch_listing.call_count == 2


def test_empty_source(collector):

    collector.fetch_listing = Mock(
        return_value=([], 0, 9)
    )

    result = collector.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 0


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("Unavailable"),
        requests.Timeout("Timeout"),
        PermissionError("Access denied"),
    ],
)
def test_listing_failure_preserves_results(
    collector, record, detail_html, error
):

    records = configure(
        collector, record, detail_html
    )

    def listing(status, page):

        if status == "upcoming":
            raise error

        return [records[status]], 1, 1

    collector.fetch_listing.side_effect = listing

    result = collector.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0


@pytest.mark.parametrize("status", [403, 429, 503])
def test_detail_failure_preserves_results(
    collector, record, detail_html, status
):

    records = configure(
        collector, record, detail_html
    )

    original_fetch = collector.fetch.side_effect

    def fetch(url):

        if url == records["upcoming"]["url"]:

            response = requests.Response()
            response.status_code = status

            raise requests.HTTPError(
                response=response
            )

        return original_fetch(url)

    collector.fetch.side_effect = fetch

    result = collector.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0


def test_initial_source_failure(collector):

    collector.fetch_listing = Mock(
        side_effect=requests.ConnectionError(
            "Unavailable"
        )
    )

    result = collector.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 0
    collector.fetch_listing.assert_called_once()


def test_malformed_status_preserves_other_status(
    collector, record, detail_html
):

    records = configure(
        collector, record, detail_html
    )

    def listing(status, page):

        if status == "open":

            raise ValueError("Malformed API payload")

        return [records[status]], 1, 1

    collector.fetch_listing.side_effect = listing

    result = collector.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1


def test_empty_page_with_remaining_records(
    collector, record, detail_html
):

    records = configure(
        collector, record, detail_html
    )

    def listing(status, page):

        if status == "open":

            return [], 10, 9

        return [records[status]], 1, 1

    collector.fetch_listing.side_effect = listing

    result = collector.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1


def test_oversized_page(
    collector, record, detail_html
):

    records = configure(
        collector, record, detail_html
    )

    collector.fetch_listing.side_effect = (
        lambda status, page: (
            [records[status], records[status]],
            10,
            1,
        )
    )

    result = collector.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 0


def test_repeated_page(
    collector, record, detail_html
):

    records = configure(
        collector, record, detail_html
    )

    collector.fetch_listing.side_effect = (
        lambda status, page: (
            [records[status]], 10, 1
        )
    )

    result = collector.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 2
    assert collector.stats["repeated_pages"] == 1


def test_invalid_record_can_be_reprocessed(
    collector, record, detail_html
):

    records = configure(
        collector, record, detail_html
    )

    invalid = deepcopy(records["open"])
    invalid["title"] = ""

    def listing(status, page):

        if status == "open":

            return [
                invalid,
                records["open"],
            ], 2, 2

        return [records[status]], 1, 1

    collector.fetch_listing.side_effect = listing

    result = collector.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 2
    assert result.rejected_count == 1


@pytest.mark.parametrize(
    "conflict",
    ["same_id", "same_url"],
)
def test_identity_conflict(
    collector, record, detail_html, conflict
):

    records = configure(
        collector, record, detail_html
    )

    if conflict == "same_id":

        records["upcoming"]["id"] = (
            records["open"]["id"]
        )

    else:

        records["upcoming"]["url"] = (
            records["open"]["url"]
        )

    result = collector.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 1

    assert collector.stats["identity_conflicts"] == 1


@pytest.mark.parametrize("status", [404, 410])
def test_missing_detail(
    collector, record, detail_html, status
):

    records = configure(
        collector, record, detail_html
    )

    original_fetch = collector.fetch.side_effect

    def fetch(url):

        if url == records["upcoming"]["url"]:

            response = requests.Response()
            response.status_code = status

            raise requests.HTTPError(
                response=response
            )

        return original_fetch(url)

    collector.fetch.side_effect = fetch

    result = collector.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 1
    assert result.rejected_count == 0
    assert collector.stats["details_missing"] == 1


def test_rejected_payload_is_minimized(
    collector, record, detail_html
):

    records = configure(
        collector, record, detail_html
    )

    records["open"]["title"] = ""
    records["open"]["unrelated_token"] = "synthetic-secret"

    result = collector.run_with_result()

    assert result.rejected_count == 1

    payload = result.invalid_records[0].raw_payload

    assert set(payload) <= {
        "id",
        "url",
        "open_state",
    }

    assert "synthetic-secret" not in str(payload)


def test_invalid_json_classification(collector):

    response = Mock()

    response.json.side_effect = (
        requests.exceptions.JSONDecodeError(
            "Invalid JSON", "", 0
        )
    )

    collector.fetch = Mock(
        return_value=response
    )

    result = collector.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR


def test_unexpected_error_propagates(collector):

    collector.fetch_listing = Mock(
        side_effect=RuntimeError(
            "Programming error"
        )
    )

    with pytest.raises(RuntimeError):

        collector.run_with_result()

    collector.client.close.assert_called_once()
