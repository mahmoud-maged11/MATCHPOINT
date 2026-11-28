
from unittest.mock import Mock

import pytest
import requests

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from test_egyincs import (
    make_record,
    make_scraper,
)


def test_source_exhausted():

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch_page = Mock(
        return_value=([make_record(1)], 1)
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 1


def test_empty_source():

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch_page = Mock(
        return_value=([], 0)
    )

    result = scraper.run_with_result()

    assert result.source_exhausted
    assert result.returned_count == 0


def test_job_limit():

    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=1,
    )

    scraper.fetch_page = Mock(
        return_value=([make_record(1)], 5)
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT


def test_page_limit():

    scraper = make_scraper(
        endpoint="jobs",
        max_pages=1,
    )

    scraper.fetch_page = Mock(
        return_value=([make_record(1)], 5)
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT


def test_duplicate_only_page():

    scraper = make_scraper(
        endpoint="jobs",
        page_size=1,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            ([make_record(1)], 3),
            ([make_record(1)], 3),
        ]
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("Connection lost"),
        requests.Timeout("Timeout"),
        PermissionError("Access denied"),
    ],
)
def test_page_failure_preserves_results(error):

    scraper = make_scraper(
        endpoint="jobs",
        page_size=1,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            ([make_record(1)], 2),
            error,
        ]
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0


def test_jobs_failure_does_not_discard_courses():

    scraper = make_scraper(
        endpoint="all",
        max_jobs=4,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            requests.ConnectionError("Jobs unavailable"),
            ([make_record(4, "lp_course")], 1),
        ]
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.accepted_count == 1

    reports = scraper.stats["endpoint_results"]

    assert not reports["jobs"]["completed"]
    assert reports["lp_course"]["completed"]


def test_courses_failure_preserves_jobs():

    scraper = make_scraper(
        endpoint="all",
        max_jobs=4,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            ([make_record(1)], 1),
            requests.ConnectionError("Courses unavailable"),
        ]
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.accepted_count == 1

    reports = scraper.stats["endpoint_results"]

    assert reports["jobs"]["completed"]
    assert not reports["lp_course"]["completed"]


def test_all_endpoints_failed():

    scraper = make_scraper(
        endpoint="all",
        max_jobs=4,
    )

    scraper.fetch_page = Mock(
        side_effect=requests.ConnectionError("Unavailable")
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.accepted_count == 0


def test_all_endpoints_exhausted():

    scraper = make_scraper(
        endpoint="all",
        max_jobs=8,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            ([make_record(1)], 1),
            ([make_record(2, "lp_course")], 1),
        ]
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 2


def test_company_failure_preserves_results():

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch_page = Mock(
        return_value=(
            [make_record(1), make_record(2)],
            1,
        )
    )

    scraper.fetch_company_name.side_effect = [
        "Test Company",
        requests.ConnectionError("Company unavailable"),
    ]

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1


def test_company_identity_error():

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch_page = Mock(
        return_value=(
            [make_record(1), make_record(2)],
            1,
        )
    )

    scraper.fetch_company_name.side_effect = [
        "Test Company",
        ValueError("Company ID mismatch"),
    ]

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1


def test_invalid_record_does_not_reserve_identity():

    scraper = make_scraper(
        endpoint="jobs",
        page_size=1,
    )

    invalid = make_record(1)
    invalid["title"]["rendered"] = ""

    scraper.fetch_page = Mock(
        side_effect=[
            ([invalid], 2),
            ([make_record(1)], 2),
        ]
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 1
    assert result.rejected_count == 1
    assert scraper.stats["duplicates"] == 0


def test_empty_page_with_remaining_pages():

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch_page = Mock(
        return_value=([], 5)
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert not result.source_exhausted


def test_invalid_json_classification():

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch = Mock()

    scraper.fetch.return_value.json.side_effect = (
        requests.exceptions.JSONDecodeError(
            "Invalid JSON",
            "invalid",
            0,
        )
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR


@pytest.mark.parametrize(
    "total_pages",
    ["-1", "invalid", "0"],
)
def test_invalid_pagination_metadata(total_pages):

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch = Mock()

    response = scraper.fetch.return_value

    response.json.return_value = [make_record(1)]

    response.headers = {
        "X-WP-TotalPages": total_pages,
    }

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR


def test_initial_network_error_propagates():

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch_page = Mock(
        side_effect=requests.ConnectionError("Unavailable")
    )

    with pytest.raises(requests.ConnectionError):

        scraper.run_with_result()

    assert scraper.last_result.status == CollectionStatus.FAILED
    assert scraper.last_result.stop_reason == StopReason.SOURCE_ERROR


def test_unexpected_error_propagates():

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch_page = Mock(
        side_effect=RuntimeError("Programming error")
    )

    with pytest.raises(RuntimeError):

        scraper.run_with_result()

    scraper.client.close.assert_called_once()
