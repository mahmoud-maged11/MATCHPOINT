from unittest.mock import Mock

import pytest
import requests

from scrapers import main as cli
from scrapers.collection_result import StopReason
from scrapers.company_cache import (
    CompanyCache,
    create_wuzzuf_company_cache,
)
from scrapers.sources.wuzzuf_api import WuzzufAPIScraper

from test_wuzzuf_api import make_job


def scraper_for(pages, **settings):

    scraper = WuzzufAPIScraper(**settings)

    scraper.fetch_page = Mock(side_effect=pages)

    scraper.fetch_company_name = Mock(
        return_value="Test Company"
    )

    return scraper


def test_unlimited_full_load():

    scraper = scraper_for(
        [
            [make_job("1"), make_job("2")],
            [make_job("3"), make_job("4")],
            [make_job("5")],
        ],
        max_jobs=None,
        max_pages=None,
        page_size=2,
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 5
    assert result.source_exhausted

    assert [
        call.args
        for call in scraper.fetch_page.call_args_list
    ] == [(0, 2), (2, 2), (4, 2)]


def test_full_load_with_empty_boundary():

    scraper = scraper_for(
        [
            [make_job("1"), make_job("2")],
            [],
        ],
        max_jobs=None,
        max_pages=None,
        page_size=2,
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 2
    assert result.source_exhausted


def test_partial_page_overlap():

    scraper = scraper_for(
        [
            [make_job("1"), make_job("2")],
            [make_job("2"), make_job("3")],
        ],
        max_jobs=None,
        max_pages=None,
        page_size=2,
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 3
    assert not result.scope_completed
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert scraper.stats["duplicates"] == 1


def test_oversized_page_is_not_successful():

    scraper = scraper_for(
        [[make_job("1"), make_job("2")]],
        max_jobs=None,
        max_pages=None,
        page_size=1,
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 0
    assert not result.scope_completed
    assert result.stop_reason == StopReason.PARSING_ERROR


@pytest.mark.parametrize(
    "settings",
    [
        {"max_jobs": True},
        {"max_pages": True},
        {"max_jobs": 0},
        {"max_pages": 0},
        {"page_size": 21},
        {"page_size": True},
    ],
)
def test_invalid_limits(settings):

    with pytest.raises(ValueError):
        WuzzufAPIScraper(**settings)


def test_cli_full_api(monkeypatch):

    monkeypatch.setenv("MATCHPOINT_COMPANY_CACHE", "0")

    parser = cli.build_parser()

    args = parser.parse_args([
        "--source", "wuzzuf",
        "--mode", "api",
        "--load-strategy", "full",
    ])

    mode = cli.validate_arguments(parser, args)

    scraper = cli.create_scraper(args, mode)

    assert isinstance(scraper, WuzzufAPIScraper)
    assert scraper.max_jobs is None
    assert scraper.max_pages is None

    scraper.client.close()


def test_cli_full_html_rejected():

    parser = cli.build_parser()

    args = parser.parse_args([
        "--source", "wuzzuf",
        "--mode", "html",
        "--load-strategy", "full",
    ])

    with pytest.raises(SystemExit):
        cli.validate_arguments(parser, args)


def test_persistent_company_cache(tmp_path):

    path = tmp_path / "wuzzuf.sqlite3"

    first = WuzzufAPIScraper(
        persistent_company_cache=CompanyCache(path)
    )

    response = Mock()

    response.json.return_value = {
        "data": {
            "id": "123",
            "attributes": {
                "name": "Test Company",
            },
        },
    }

    first.client.get = Mock(return_value=response)

    assert first.fetch_company_name("123") == "Test Company"

    second = WuzzufAPIScraper(
        persistent_company_cache=CompanyCache(path)
    )

    second.client.get = Mock(
        side_effect=AssertionError("Unexpected HTTP request")
    )

    assert second.fetch_company_name("123") == "Test Company"

    second.client.get.assert_not_called()

    first.client.close()
    second.client.close()


def test_access_denial_not_cached(tmp_path):

    cache = CompanyCache(tmp_path / "wuzzuf.sqlite3")

    scraper = WuzzufAPIScraper(
        persistent_company_cache=cache
    )

    response = Mock()
    response.status_code = 403

    scraper.client.get = Mock(
        side_effect=requests.HTTPError(response=response)
    )

    with pytest.raises(requests.HTTPError):
        scraper.fetch_company_name("123")

    assert cache.get("123") == (False, None)

    scraper.client.close()


def test_cache_namespace(tmp_path, monkeypatch):

    monkeypatch.setenv("MATCHPOINT_COMPANY_CACHE", "1")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    monkeypatch.delenv(
        "MATCHPOINT_WUZZUF_COMPANY_CACHE_PATH",
        raising=False,
    )

    cache = create_wuzzuf_company_cache()

    assert cache.path.name == "wuzzuf_companies.sqlite3"
