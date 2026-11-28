
from copy import deepcopy
from unittest.mock import Mock

import pytest
import requests

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from test_un_volunteers import (
    scraper,
    listing,
    detail,
    lookup,
)


def configure(scraper, listing, detail):

    scraper.client.session.request = Mock(
        side_effect=AssertionError(
            "Unexpected real HTTP request"
        )
    )

    records = [
        {**deepcopy(listing), "id": 101},
        {**deepcopy(listing), "id": 102},
    ]

    details = {
        item["id"]: {
            **deepcopy(detail),
            "id": item["id"],
            "sourcingEndDate": "2099-12-31T00:00:00",
        }
        for item in records
    }

    scraper.fetch_listing = Mock(
        return_value=(records, len(records))
    )

    scraper.fetch_detail = Mock(
        side_effect=lambda record_id: deepcopy(
            details[record_id]
        )
    )

    return records, details


def test_source_exhausted(scraper, listing, detail):

    configure(scraper, listing, detail)

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 2
    assert scraper.stats["processed"] == 2
    assert scraper.stats["unprocessed"] == 0


def test_empty_source(scraper):

    scraper.fetch_listing = Mock(
        return_value=([], 0)
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 0


def test_requested_job_limit(scraper, listing, detail):

    configure(scraper, listing, detail)

    scraper.max_jobs = 1

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert result.accepted_count == 1
    assert scraper.stats["processed"] == 1
    assert scraper.stats["unprocessed"] == 1

    scraper.fetch_detail.assert_called_once_with(101)


def test_requested_page_limit(scraper, listing, detail):

    records, _ = configure(
        scraper, listing, detail
    )

    scraper.max_pages = 1

    scraper.fetch_listing.return_value = (
        records, 100
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert result.accepted_count == 2

    scraper.fetch_listing.assert_called_once_with(0)


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("Unavailable"),
        requests.Timeout("Timeout"),
        PermissionError("Access denied"),
    ],
)
def test_listing_failure_preserves_results(
    scraper, listing, detail, error
):

    records, _ = configure(
        scraper, listing, detail
    )

    scraper.fetch_listing.side_effect = [
        (records, 100),
        error,
    ]

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 2
    assert result.rejected_count == 0


@pytest.mark.parametrize(
    "status",
    [401, 403, 429, 500],
)
def test_detail_failure_preserves_results(
    scraper, listing, detail, status
):

    _, details = configure(
        scraper, listing, detail
    )

    response = requests.Response()
    response.status_code = status

    scraper.fetch_detail.side_effect = [
        details[101],
        requests.HTTPError(response=response),
    ]

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0
    assert scraper.stats["unprocessed"] == 1


def test_initial_source_failure(scraper):

    scraper.fetch_listing = Mock(
        side_effect=requests.ConnectionError(
            "Unavailable"
        )
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 0

    scraper.fetch_listing.assert_called_once()


def test_malformed_listing_preserves_results(
    scraper, listing, detail
):

    records, _ = configure(
        scraper, listing, detail
    )

    scraper.fetch_listing.side_effect = [
        (records, 100),
        ValueError("Malformed listing"),
    ]

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 2


def test_malformed_detail_preserves_results(
    scraper, listing, detail
):

    _, details = configure(
        scraper, listing, detail
    )

    scraper.fetch_detail.side_effect = [
        details[101],
        ValueError("Malformed API detail"),
    ]

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0


def test_empty_page_with_remaining_records(
    scraper, listing, detail
):

    records, _ = configure(
        scraper, listing, detail
    )

    scraper.fetch_listing.side_effect = [
        (records, 100),
        ([], 100),
    ]

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 2


def test_repeated_page(scraper, listing, detail):

    records, _ = configure(
        scraper, listing, detail
    )

    scraper.fetch_listing.side_effect = [
        (records, 100),
        (list(reversed(records)), 100),
    ]

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 2

    assert scraper.stats["repeated_pages"] == 1
    assert scraper.fetch_detail.call_count == 2


def test_pagination_total_changes(
    scraper, listing, detail
):

    records, _ = configure(
        scraper, listing, detail
    )

    scraper.fetch_listing.side_effect = [
        ([records[0]], 10),
        ([records[1]], 2),
    ]

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 2
    assert scraper.stats["total_changes"] == 1

    assert [
        call.args[0]
        for call in scraper.fetch_listing.call_args_list
    ] == [0, 1]


@pytest.mark.parametrize(
    "total",
    [0, 1],
)
def test_contradictory_total(
    scraper, listing, detail, total
):

    records, _ = configure(
        scraper, listing, detail
    )

    scraper.fetch_listing.return_value = (
        records, total
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR

    scraper.fetch_detail.assert_not_called()


def test_invalid_identity_can_be_reprocessed(
    scraper, listing, detail
):

    records, details = configure(
        scraper, listing, detail
    )

    invalid = {
        **details[101],
        "id": 999,
    }

    scraper.fetch_listing.return_value = (
        [records[0], records[0], records[1]],
        3,
    )

    scraper.fetch_detail.side_effect = [
        invalid,
        details[101],
        details[102],
    ]

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 2
    assert result.rejected_count == 1

    assert scraper.fetch_detail.call_count == 3


@pytest.mark.parametrize(
    "status",
    [404, 410],
)
def test_missing_detail_is_not_source_failure(
    scraper, listing, detail, status
):

    _, details = configure(
        scraper, listing, detail
    )

    response = requests.Response()
    response.status_code = status

    scraper.fetch_detail.side_effect = [
        details[101],
        requests.HTTPError(response=response),
    ]

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 1
    assert result.rejected_count == 0
    assert scraper.stats["details_missing"] == 1


def test_geographic_filter_preserved(
    scraper, listing, detail
):

    records, _ = configure(
        scraper, listing, detail
    )

    records[1]["isOnsite"] = True

    records[1]["country"] = lookup(
        "Cameroon", "CMR"
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 1
    assert scraper.stats["excluded"] == 1

    scraper.fetch_detail.assert_called_once_with(101)


@pytest.mark.parametrize(
    "modality",
    [None, "false", 0, 1],
)
def test_invalid_modality_is_rejected(
    scraper, listing, detail, modality
):

    records, _ = configure(
        scraper, listing, detail
    )

    records[1]["isOnsite"] = modality

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 1
    assert result.rejected_count == 1

    scraper.fetch_detail.assert_called_once_with(101)


def test_invalid_json_classification(scraper):

    response = Mock()
    response.status_code = 200
    response.headers = {
        "Content-Type": "application/json"
    }

    response.json.side_effect = (
        requests.exceptions.JSONDecodeError(
            "Invalid JSON", "", 0
        )
    )

    scraper.client.rate_limiter.wait = Mock()

    scraper.client.session.request = Mock(
        return_value=response
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR


def test_api_failure_classification(scraper):

    response = Mock()
    response.status_code = 200
    response.headers = {
        "Content-Type": "application/json"
    }

    response.json.return_value = {
        "isSuccess": False,
        "value": None,
    }

    scraper.client.rate_limiter.wait = Mock()

    scraper.client.session.request = Mock(
        return_value=response
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.SOURCE_ERROR

    scraper.client.session.request.assert_called_once()


def test_unexpected_http_status(scraper):

    response = Mock()
    response.status_code = 302

    scraper.client.rate_limiter.wait = Mock()

    scraper.client.session.request = Mock(
        return_value=response
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.SOURCE_ERROR

    scraper.client.session.request.assert_called_once()

    assert (
        scraper.client.session.request.call_args
        .kwargs["allow_redirects"] is False
    )


@pytest.mark.parametrize(
    "offset",
    [False, 0.0, "0", None],
)
def test_invalid_offset_type(scraper, offset):

    scraper.request_json = Mock(
        return_value={
            "result": [],
            "total": 0,
            "skip": offset,
        }
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR


def test_rejected_payload_is_minimized(
    scraper, listing, detail
):

    records, details = configure(
        scraper, listing, detail
    )

    records[0]["private_token"] = "synthetic-secret"

    details[101]["name"] = None

    result = scraper.run_with_result()

    assert result.rejected_count == 1

    invalid = result.invalid_records[0]

    assert invalid.raw_payload == {
        "assignment_id": 101
    }

    assert "synthetic-secret" not in (
        invalid.model_dump_json()
    )


def test_unexpected_error_propagates(scraper):

    scraper.fetch_listing = Mock(
        side_effect=RuntimeError(
            "Programming error"
        )
    )

    scraper.client.close = Mock()

    with pytest.raises(RuntimeError):

        scraper.run_with_result()

    scraper.client.close.assert_called_once()


def test_automatic_retries_remain_disabled(scraper):

    adapter = scraper.client.session.get_adapter(
        scraper.SEARCH_URL
    )

    assert adapter.max_retries.total == 0
