
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from scrapers.incremental_window import IncrementalWindow
from scrapers.sources.egyincs import EgyincsScraper
from scrapers.collection_result import StopReason

from test_egyincs import make_record, make_scraper


NOW = datetime(
    2026, 11, 27, 12, 0, tzinfo=timezone.utc
)

WINDOW = IncrementalWindow.from_checkpoint(
    NOW - timedelta(hours=1),
    now=NOW,
)


def record(source_id, endpoint="jobs"):

    value = make_record(source_id, endpoint)

    value["modified_gmt"] = "2026-11-27T11:30:00"

    return value


def response(records, total, pages):

    result = Mock()

    result.json.return_value = records

    result.headers = {
        "X-WP-Total": str(total),
        "X-WP-TotalPages": str(pages),
    }

    return result


def scraper_for(endpoint="jobs", **limits):

    options = {
        "max_jobs": None,
        "max_pages": None,
        "page_size": 2,
    }

    options.update(limits)

    scraper = make_scraper(
        endpoint=endpoint,
        **options,
    )

    scraper.incremental_window = WINDOW

    return scraper


def test_constructor_accepts_window():

    scraper = EgyincsScraper(
        endpoint="jobs",
        incremental_window=WINDOW,
    )

    try:
        assert scraper.incremental_window == WINDOW

    finally:
        scraper.client.close()


def test_constructor_rejects_all():

    with pytest.raises(ValueError):

        EgyincsScraper(
            endpoint="all",
            incremental_window=WINDOW,
        )


def test_constructor_rejects_invalid_window():

    with pytest.raises(TypeError):

        EgyincsScraper(
            endpoint="jobs",
            incremental_window="invalid",
        )


@pytest.mark.parametrize(
    "endpoint",
    ["jobs", "lp_course"],
)
def test_incremental_complete(endpoint):

    scraper = scraper_for(endpoint)

    scraper.fetch = Mock(
        side_effect=[
            response(
                [record(1, endpoint), record(2, endpoint)],
                3,
                2,
            ),
            response(
                [record(3, endpoint)],
                3,
                2,
            ),
        ]
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 3
    assert result.source_exhausted
    assert scraper.incremental_coverage_verified(result)

    assert scraper.fetch.call_count == 2

    for call in scraper.fetch.call_args_list:

        called_endpoint, params = call.args

        assert called_endpoint == endpoint
        assert params["per_page"] == 2

        assert params["modified_after"] == (
            "2026-11-27T10:55:00Z"
        )

        assert params["modified_before"] == (
            "2026-11-27T11:58:00Z"
        )

        assert params["orderby"] == "id"
        assert params["order"] == "asc"
        assert "modified_gmt" in params["_fields"]


def test_empty_incremental_window():

    scraper = scraper_for()

    scraper.fetch = Mock(
        return_value=response([], 0, 0)
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 0
    assert result.source_exhausted
    assert scraper.incremental_coverage_verified(result)


def test_limited_window_cannot_verify():

    scraper = scraper_for(max_pages=1)

    scraper.fetch = Mock(
        return_value=response(
            [record(1), record(2)],
            3,
            2,
        )
    )

    result = scraper.run_with_result()

    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert not scraper.incremental_coverage_verified(result)


def test_rejected_record_blocks_coverage():

    scraper = scraper_for()

    invalid = record(1)
    invalid["title"]["rendered"] = ""

    scraper.fetch = Mock(
        return_value=response(
            [invalid, record(2)],
            2,
            1,
        )
    )

    result = scraper.run_with_result()

    assert result.rejected_count == 1
    assert result.accepted_count == 1
    assert not scraper.incremental_coverage_verified(result)


def test_unpublished_record_blocks_coverage():

    scraper = scraper_for()

    unpublished = record(1)
    unpublished["status"] = "draft"

    scraper.fetch = Mock(
        return_value=response(
            [unpublished, record(2)],
            2,
            1,
        )
    )

    result = scraper.run_with_result()

    assert not scraper.incremental_coverage_verified(result)


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate",
        "changed_total",
        "outside_window",
        "missing_timestamp",
        "missing_headers",
    ],
)
def test_inconsistent_second_page(failure):

    scraper = scraper_for()

    second_record = record(3)

    second = response([second_record], 3, 2)

    if failure == "duplicate":
        second_record["id"] = 1

    elif failure == "changed_total":
        second.headers["X-WP-Total"] = "4"

    elif failure == "outside_window":
        second_record["modified_gmt"] = (
            "2026-11-27T12:30:00"
        )

    elif failure == "missing_timestamp":
        del second_record["modified_gmt"]

    elif failure == "missing_headers":
        del second.headers["X-WP-Total"]

    scraper.fetch = Mock(
        side_effect=[
            response([record(1), record(2)], 3, 2),
            second,
        ]
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 2
    assert not result.source_exhausted
    assert not scraper.incremental_coverage_verified(result)


def test_legacy_collection_parameters_unchanged():

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch = Mock(
        return_value=response(
            [make_record(1)],
            1,
            1,
        )
    )

    result = scraper.run_with_result()

    params = scraper.fetch.call_args.args[1]

    assert result.accepted_count == 1
    assert params["orderby"] == "date"
    assert "modified_after" not in params
    assert "modified_before" not in params
    assert not scraper.incremental_coverage_verified(result)
