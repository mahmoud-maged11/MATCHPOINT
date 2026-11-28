
from unittest.mock import Mock

import pytest

from scrapers.collection_result import StopReason

from scrapers.sources.devpost import DevpostScraper

from scrapers.sources.devpost_mapper import (
    DevpostExcludedOpportunity,
    DevpostEligibilityUnverified,
    extract_eligibility,
)

from scrapers.main import (
    build_parser,
    validate_arguments,
    create_scraper,
)

from bs4 import BeautifulSoup

from test_devpost import record, detail_html

from test_devpost_completeness import (
    collector,
    configure,
)


def test_unlimited_constructor():

    scraper = DevpostScraper(
        max_jobs=None,
        max_pages=None,
    )

    try:
        assert scraper.max_jobs is None
        assert scraper.max_pages is None
    finally:
        scraper.client.close()


def test_full_cli():

    parser = build_parser()

    args = parser.parse_args([
        "--source", "devpost",
        "--mode", "api",
        "--load-strategy", "full",
    ])

    mode = validate_arguments(parser, args)

    assert args.max_jobs is None
    assert args.max_pages is None

    scraper = create_scraper(args, mode)

    try:
        assert scraper.max_jobs is None
        assert scraper.max_pages is None
    finally:
        scraper.client.close()


def test_full_source_exhaustion(
    collector, record, detail_html
):

    configure(
        collector, record, detail_html
    )

    collector.max_jobs = None
    collector.max_pages = None

    result = collector.run_with_result()

    assert result.source_exhausted
    assert result.accepted_count == 2


@pytest.mark.parametrize(
    "total,per_page",
    [
        (2, 2),
        (20, 9),
        (9, 9),
    ],
)
def test_short_page_not_exhausted(
    collector, record, detail_html,
    total, per_page,
):

    records = configure(
        collector, record, detail_html
    )

    def listing(status, page):

        if status == "open":
            return [records[status]], total, per_page

        return [records[status]], 1, 1

    collector.fetch_listing.side_effect = listing

    result = collector.run_with_result()

    assert not result.source_exhausted

    assert result.stop_reason == (
        StopReason.PARSING_ERROR
    )

    assert result.accepted_count == 1

    assert collector.stats[
        "pagination_anomalies"
    ] == 1


@pytest.mark.parametrize(
    "second_total,second_size",
    [
        (3, 1),
        (2, 2),
    ],
)
def test_pagination_metadata_drift(
    collector, record, detail_html,
    second_total, second_size,
):

    records = configure(
        collector, record, detail_html
    )

    def listing(status, page):

        if status == "upcoming":
            return [records[status]], 1, 1

        if page == 1:
            return [records[status]], 2, 1

        return [
            records[status]
        ], second_total, second_size

    collector.fetch_listing.side_effect = listing

    result = collector.run_with_result()

    assert not result.source_exhausted

    assert result.stop_reason == (
        StopReason.PARSING_ERROR
    )

    assert collector.stats[
        "pagination_anomalies"
    ] == 1


@pytest.mark.parametrize(
    "title",
    [
        "Specific countries excluded",
        "Only specific countries included",
    ],
)
def test_unverified_country_list(title):

    soup = BeautifulSoup(
        f"""
        <h3 id="eligibility-countries-modal-title">
            {title}
        </h3>
        <ul id="eligibility-countries-modal-list">
        </ul>
        """,
        "html.parser",
    )

    with pytest.raises(
        DevpostEligibilityUnverified
    ):
        extract_eligibility(soup)


def test_explicit_egypt_exclusion():

    soup = BeautifulSoup(
        """
        <h3 id="eligibility-countries-modal-title">
            Specific countries excluded
        </h3>
        <ul id="eligibility-countries-modal-list">
            <li>Egypt</li>
        </ul>
        """,
        "html.parser",
    )

    with pytest.raises(
        DevpostExcludedOpportunity
    ) as error:
        extract_eligibility(soup)

    assert not isinstance(
        error.value,
        DevpostEligibilityUnverified,
    )


def test_unverified_eligibility_counted(
    collector, record, detail_html
):

    configure(
        collector, record, detail_html
    )

    original_fetch = collector.fetch.side_effect

    def fetch(url):

        response = original_fetch(url)

        response.text = (
            response.text
            .replace("<li>Cuba</li>", "")
            .replace("<li>Iran</li>", "")
        )

        return response

    collector.fetch.side_effect = fetch

    result = collector.run_with_result()

    assert result.accepted_count == 0

    assert collector.stats[
        "eligibility_unverified"
    ] == 2

    assert collector.stats["excluded"] == 2
