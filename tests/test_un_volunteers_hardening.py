from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from scrapers import main as cli
from scrapers.collection_result import StopReason
from scrapers.sources.un_volunteers import UNVolunteersScraper
from scrapers.sources.un_volunteers_mapper import resolve_status


@pytest.fixture
def collector():

    scraper = UNVolunteersScraper(
        max_jobs=None,
        max_pages=None,
        page_size=2,
    )

    # Exercise pagination independently of mapping.
    # No network requests are permitted.
    scraper.collect_record = Mock(return_value=None)

    yield scraper

    scraper.client.session.close()


def records(*ids):

    return [{"id": value} for value in ids]


def test_unlimited_collection(collector):

    collector.fetch_listing = Mock(
        side_effect=[
            (records(1, 2), 5),
            (records(3, 4), 5),
            (records(5), 5),
        ]
    )

    result = collector.run_with_result()

    assert result.source_exhausted
    assert collector.stats["processed"] == 5

    assert [
        call.args[0]
        for call in collector.fetch_listing.call_args_list
    ] == [0, 2, 4]


@pytest.mark.parametrize(
    "total",
    [0, 1, 3, 4, 100],
)
def test_total_drift(collector, total):

    collector.fetch_listing = Mock(
        side_effect=[
            (records(1, 2), 5),
            (records(3, 4), total),
        ]
    )

    result = collector.run_with_result()

    assert not result.source_exhausted
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert collector.stats["total_changes"] == 1
    assert collector.stats["processed"] == 2


def test_short_nonterminal_page(collector):

    collector.fetch_listing = Mock(
        return_value=(records(1), 5)
    )

    result = collector.run_with_result()

    assert result.stop_reason == StopReason.PARSING_ERROR
    assert collector.stats["pagination_anomalies"] == 1
    collector.collect_record.assert_not_called()


def test_partial_overlap(collector):

    collector.fetch_listing = Mock(
        side_effect=[
            (records(1, 2), 4),
            (records(2, 3), 4),
        ]
    )

    result = collector.run_with_result()

    assert result.stop_reason == StopReason.PARSING_ERROR
    assert collector.stats["overlapping_pages"] == 1
    assert collector.stats["processed"] == 2


def test_duplicate_ids_inside_page(collector):

    collector.fetch_listing = Mock(
        return_value=(records(1, 1), 2)
    )

    result = collector.run_with_result()

    assert result.stop_reason == StopReason.PARSING_ERROR
    collector.collect_record.assert_not_called()


@pytest.mark.parametrize(
    "invalid_id",
    [None, True, 0, -1, "123"],
)
def test_invalid_pagination_identity(
    collector, invalid_id
):

    collector.fetch_listing = Mock(
        return_value=(records(1, invalid_id), 2)
    )

    result = collector.run_with_result()

    assert result.stop_reason == StopReason.PARSING_ERROR
    collector.collect_record.assert_not_called()


def test_repeated_full_page(collector):

    collector.fetch_listing = Mock(
        side_effect=[
            (records(1, 2), 4),
            (records(2, 1), 4),
        ]
    )

    result = collector.run_with_result()

    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert collector.stats["repeated_pages"] == 1


def test_empty_full_scope(collector):

    collector.fetch_listing = Mock(
        return_value=([], 0)
    )

    result = collector.run_with_result()

    assert result.source_exhausted


def test_maximum_calendar_deadline():

    detail = {
        "status": {"code": "DOA_SOURCING"},
        "isSourcingActive": True,
        "isReserved": False,
        "isSingleSource": False,
        "sourcingEndDate": "9999-12-31T00:00:00",
    }

    assert resolve_status(
        detail,
        datetime(2026, 11, 28, tzinfo=timezone.utc),
    ) == "active"


def test_full_cli():

    parser = cli.build_parser()

    args = parser.parse_args([
        "--source", "un_volunteers",
        "--mode", "api",
        "--storage", "json",
        "--load-strategy", "full",
    ])

    mode = cli.validate_arguments(parser, args)

    assert args.max_jobs is None
    assert args.max_pages is None

    scraper = cli.create_scraper(args, mode)

    try:
        assert scraper.max_jobs is None
        assert scraper.max_pages is None
    finally:
        scraper.client.session.close()
