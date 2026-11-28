import requests

from test_forasna import (
    SEARCH,
    NEXT,
    job_url,
    search_html,
    detail_html,
    make_scraper,
)

from scrapers.collection_result import StopReason


def test_unlimited_collection_exhaustion():

    scraper = make_scraper({
        SEARCH: search_html([1, 2], NEXT),
        NEXT: search_html([3, 4]),
        **{
            job_url(i): detail_html(i)
            for i in range(1, 5)
        },
    }, max_jobs=None, max_pages=None)

    result = scraper.run_with_result()

    assert result.source_exhausted
    assert result.scope_completed
    assert result.accepted_count == 4
    assert scraper.stats["pages"] == 2
    assert scraper.stats["details_fetched"] == 4
    assert scraper.client.get.call_count == 7


def test_unlimited_overlap_is_not_verified_exhaustion():

    scraper = make_scraper({
        SEARCH: search_html([1, 2], NEXT),
        NEXT: search_html([2, 3]),
        **{
            job_url(i): detail_html(i)
            for i in range(1, 4)
        },
    }, max_jobs=None, max_pages=None)

    result = scraper.run_with_result()

    assert result.accepted_count == 3
    assert not result.scope_completed
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert scraper.stats["pagination_overlaps"] == 1
    assert scraper.stats["details_fetched"] == 3


def test_unlimited_network_failure_preserves_records():

    scraper = make_scraper({
        SEARCH: search_html([1, 2], NEXT),
        NEXT: requests.ConnectionError("network failure"),
        job_url(1): detail_html(1),
        job_url(2): detail_html(2),
    }, max_jobs=None, max_pages=None)

    result = scraper.run_with_result()

    assert result.accepted_count == 2
    assert not result.scope_completed
    assert result.stop_reason == StopReason.SOURCE_ERROR


def test_unlimited_repeated_page_stops():

    scraper = make_scraper({
        SEARCH: search_html([1], SEARCH),
        job_url(1): detail_html(1),
    }, max_jobs=None, max_pages=None)

    result = scraper.run_with_result()

    assert result.accepted_count == 1
    assert not result.scope_completed
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert scraper.stats["pages"] == 1


def test_country_classification():

    scraper = make_scraper({
        SEARCH: search_html([1, 2, 3]),
        job_url(1): detail_html(1, country="EG"),
        job_url(2): detail_html(2, country="AE"),
        job_url(3): detail_html(3, country=None),
    }, max_jobs=None, max_pages=None)

    result = scraper.run_with_result()

    assert result.accepted_count == 1
    assert scraper.stats["non_egyptian"] == 1
    assert scraper.stats["unknown_country"] == 1
    assert result.rejected_count == 0


def test_single_parse_per_detail(monkeypatch):

    import scrapers.sources.forasna as scraper_module
    import scrapers.sources.forasna_mapper as mapper_module

    original = mapper_module.BeautifulSoup

    detail_parses = []

    def tracked_parser(html, *args, **kwargs):

        if 'JobPosting' in html:
            detail_parses.append(1)

        return original(html, *args, **kwargs)

    monkeypatch.setattr(
        scraper_module,
        "BeautifulSoup",
        tracked_parser,
    )

    monkeypatch.setattr(
        mapper_module,
        "BeautifulSoup",
        tracked_parser,
    )

    scraper = make_scraper({
        SEARCH: search_html([1, 2]),
        job_url(1): detail_html(1),
        job_url(2): detail_html(2),
    }, max_jobs=None, max_pages=None)

    result = scraper.run_with_result()

    assert result.accepted_count == 2
    assert len(detail_parses) == 2
