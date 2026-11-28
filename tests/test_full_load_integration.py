from unittest.mock import Mock

import pytest

from scrapers import main as cli
from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from test_egyincs import make_record, make_scraper


def parse(*arguments):
    parser = cli.build_parser()
    args = parser.parse_args(arguments)
    mode = cli.validate_arguments(parser, args)
    return args, mode


def test_bounded_defaults():
    args, mode = parse("--source", "egyincs")

    assert mode == "api"
    assert args.load_strategy == "bounded"
    assert args.max_jobs == 20
    assert args.max_pages == 10
    assert args.page_size == 20


def test_full_defaults():
    args, mode = parse(
        "--source", "egyincs",
        "--load-strategy", "full",
    )

    assert args.max_jobs is None
    assert args.max_pages is None

    scraper = cli.create_scraper(args, mode)

    assert scraper.max_jobs is None
    assert scraper.max_pages is None


def test_full_explicit_limits():
    args, _ = parse(
        "--source", "egyincs",
        "--load-strategy", "full",
        "--max-jobs", "100",
        "--max-pages", "30",
    )

    assert args.max_jobs == 100
    assert args.max_pages == 30


FULL_SOURCE_MODES = [
    ("egyincs", "api"),
    ("devpost", "api"),
    ("un_volunteers", "api"),
    ("wuzzuf", "api"),
    ("forasna", "live"),
    ("itida", "live"),
    ("nti", "live"),
    ("bayt", "live"),
]


@pytest.mark.parametrize(
    "source, expected_mode",
    FULL_SOURCE_MODES,
)
def test_supported_full_source(source, expected_mode):
    args, mode = parse(
        "--source", source,
        "--mode", expected_mode,
        "--load-strategy", "full",
    )

    assert mode == expected_mode
    assert args.source == source
    assert args.load_strategy == "full"
    assert args.max_jobs is None
    assert args.max_pages is None


def test_full_load_source_contract_covers_all_sources():
    assert set(cli.SOURCES) == {
        source for source, _ in FULL_SOURCE_MODES
    }


@pytest.mark.parametrize(
    "source, expected_mode",
    FULL_SOURCE_MODES,
)
def test_full_source_preserves_explicit_limits(
    source, expected_mode
):
    args, mode = parse(
        "--source", source,
        "--mode", expected_mode,
        "--load-strategy", "full",
        "--max-jobs", "100",
        "--max-pages", "30",
    )

    assert mode == expected_mode
    assert args.load_strategy == "full"
    assert args.max_jobs == 100
    assert args.max_pages == 30


def test_wuzzuf_full_rejects_html_mode():
    with pytest.raises(SystemExit) as error:
        parse(
            "--source", "wuzzuf",
            "--mode", "html",
            "--load-strategy", "full",
        )

    assert error.value.code == 2


def test_incremental_requires_persistent_storage():
    with pytest.raises(SystemExit) as error:
        parse(
            "--source", "egyincs",
            "--load-strategy", "incremental",
        )

    assert error.value.code == 2


def test_recovery_rejects_strategy():
    with pytest.raises(SystemExit) as error:
        parse(
            "--recover-run-id",
            "11111111-1111-4111-8111-000000000001",
            "--load-strategy", "full",
        )

    assert error.value.code == 2


def test_full_collection_exceeds_legacy_limits():
    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=None,
        max_pages=None,
        page_size=2,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            (
                [
                    make_record(page * 2 - 1),
                    make_record(page * 2),
                ],
                15,
            )
            for page in range(1, 16)
        ]
    )

    result = scraper.run_with_result()

    assert result.source_exhausted
    assert result.accepted_count == 30
    assert scraper.fetch_page.call_count == 15


def test_full_all_endpoints():
    scraper = make_scraper(
        endpoint="all",
        max_jobs=None,
        max_pages=None,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            ([make_record(1)], 1),
            ([make_record(2, "lp_course")], 1),
        ]
    )

    result = scraper.run_with_result()

    assert result.source_exhausted
    assert result.accepted_count == 2

    assert scraper.stats["jobs"] == 1
    assert scraper.stats["lp_course"] == 1


def test_full_with_page_safety_limit():
    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=None,
        max_pages=1,
    )

    scraper.fetch_page = Mock(
        return_value=([make_record(1)], 3)
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert not result.source_exhausted
    assert result.stop_reason == StopReason.REQUESTED_LIMIT


def test_full_with_job_safety_limit():
    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=1,
        max_pages=None,
    )

    scraper.fetch_page = Mock(
        return_value=([make_record(1)], 3)
    )

    result = scraper.run_with_result()

    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert not result.source_exhausted


def test_full_without_pagination_headers():
    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=None,
        max_pages=None,
        page_size=2,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            ([make_record(1), make_record(2)], None),
            ([make_record(3)], None),
        ]
    )

    result = scraper.run_with_result()

    assert result.source_exhausted
    assert result.accepted_count == 3


def test_repeated_invalid_page_stops_collection():
    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=None,
        max_pages=None,
        page_size=1,
    )

    invalid = make_record(1)
    invalid["title"]["rendered"] = ""

    scraper.fetch_page = Mock(
        side_effect=[
            ([invalid], None),
            ([invalid], None),
        ]
    )

    result = scraper.run_with_result()

    assert not result.source_exhausted
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.rejected_count == 1
    assert scraper.fetch_page.call_count == 2


def test_reordered_duplicate_page():
    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=None,
        max_pages=None,
        page_size=2,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            ([make_record(1), make_record(2)], None),
            ([make_record(2), make_record(1)], None),
        ]
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 2


def test_skipped_endpoint_not_source_exhausted():
    scraper = make_scraper(
        endpoint="all",
        max_jobs=2,
    )

    scraper.fetch_page = Mock(
        return_value=([make_record(1)], 1)
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert not result.source_exhausted
    assert result.stop_reason == StopReason.REQUESTED_LIMIT

    assert (
        scraper.stats["endpoint_results"]["lp_course"]["pages"]
        == 0
    )
