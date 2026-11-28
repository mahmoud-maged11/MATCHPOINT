from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
import requests

from scrapers.company_cache import (
    CompanyCache,
    create_egyincs_company_cache,
)

from scrapers.sources.egyincs import EgyincsScraper


@pytest.fixture
def scraper_factory():

    scrapers = []

    def create(cache):

        scraper = EgyincsScraper(
            max_jobs=1,
            max_pages=1,
            page_size=1,
            endpoint="jobs",
            persistent_company_cache=cache,
        )

        scrapers.append(scraper)

        return scraper

    yield create

    for scraper in scrapers:
        scraper.client.close()


def response(company_id=1, name="Example Company"):

    result = Mock()

    result.json.return_value = {
        "id": company_id,
        "title": {"rendered": name},
    }

    return result


def test_cache_miss(tmp_path):

    cache = CompanyCache(tmp_path / "cache.db")

    assert cache.get("1") == (False, None)


def test_unicode_persistence(tmp_path):

    path = tmp_path / "cache.db"

    name = "\u0634\u0631\u0643\u0629"

    assert CompanyCache(path).put("1", name)

    assert CompanyCache(path).get("1") == (
        True, name
    )


@pytest.mark.parametrize(
    "name,ttl",
    [
        ("Company", 86400),
        (None, 3600),
    ],
)
def test_expiration(tmp_path, name, ttl):

    now = [100000]

    cache = CompanyCache(
        tmp_path / "cache.db",
        clock=lambda: now[0],
    )

    assert cache.put("1", name)

    now[0] += ttl - 1

    assert cache.get("1") == (True, name)

    now[0] += 1

    assert cache.get("1") == (False, None)


def test_upsert(tmp_path):

    cache = CompanyCache(tmp_path / "cache.db")

    assert cache.put("1", None)
    assert cache.put("1", "New Name")

    assert cache.get("1") == (
        True, "New Name"
    )


def test_empty_name(tmp_path):

    cache = CompanyCache(tmp_path / "cache.db")

    assert not cache.put("1", " ")

    assert cache.get("1") == (False, None)


def test_prune(tmp_path):

    now = [100000]

    cache = CompanyCache(
        tmp_path / "cache.db",
        clock=lambda: now[0],
    )

    cache.put("1", None)
    cache.put("2", "Company")

    now[0] += 3600

    assert cache.prune() == 1

    assert cache.get("1") == (False, None)
    assert cache.get("2") == (True, "Company")


def test_concurrent_writes(tmp_path):

    path = tmp_path / "cache.db"

    assert CompanyCache(path).put("0", "Initial")

    def write(index):

        return CompanyCache(path).put(
            str(index),
            f"Company {index}",
        )

    with ThreadPoolExecutor(
        max_workers=4
    ) as executor:

        assert all(
            executor.map(write, range(1, 41))
        )

    cache = CompanyCache(path)

    for index in range(1, 41):

        assert cache.get(str(index)) == (
            True,
            f"Company {index}",
        )


def test_cross_run_cache(
    tmp_path,
    monkeypatch,
    scraper_factory,
):

    path = tmp_path / "cache.db"

    first = scraper_factory(CompanyCache(path))
    second = scraper_factory(CompanyCache(path))

    fetch_first = Mock(return_value=response())
    fetch_second = Mock()

    monkeypatch.setattr(first, "fetch", fetch_first)
    monkeypatch.setattr(second, "fetch", fetch_second)

    assert first.fetch_company_name(1) == "Example Company"
    assert first.fetch_company_name(1) == "Example Company"
    assert second.fetch_company_name(1) == "Example Company"

    fetch_first.assert_called_once()
    fetch_second.assert_not_called()


def test_negative_cache(
    tmp_path,
    monkeypatch,
    scraper_factory,
):

    path = tmp_path / "cache.db"

    first = scraper_factory(CompanyCache(path))
    second = scraper_factory(CompanyCache(path))

    error_response = requests.Response()
    error_response.status_code = 404

    fetch_first = Mock(
        side_effect=requests.HTTPError(
            response=error_response
        )
    )

    fetch_second = Mock()

    monkeypatch.setattr(first, "fetch", fetch_first)
    monkeypatch.setattr(second, "fetch", fetch_second)

    assert first.fetch_company_name(1) is None
    assert second.fetch_company_name(1) is None

    fetch_first.assert_called_once()
    fetch_second.assert_not_called()

    assert CompanyCache(path).get("1") == (
        True, None
    )


@pytest.mark.parametrize("status", [429, 500, 503])
def test_http_error_not_cached(
    tmp_path,
    monkeypatch,
    scraper_factory,
    status,
):

    cache = CompanyCache(tmp_path / "cache.db")

    scraper = scraper_factory(cache)

    error_response = requests.Response()
    error_response.status_code = status

    monkeypatch.setattr(
        scraper,
        "fetch",
        Mock(
            side_effect=requests.HTTPError(
                response=error_response
            )
        ),
    )

    with pytest.raises(requests.HTTPError):

        scraper.fetch_company_name(1)

    assert cache.get("1") == (False, None)


def test_timeout_not_cached(
    tmp_path,
    monkeypatch,
    scraper_factory,
):

    cache = CompanyCache(tmp_path / "cache.db")

    scraper = scraper_factory(cache)

    monkeypatch.setattr(
        scraper,
        "fetch",
        Mock(side_effect=requests.Timeout()),
    )

    with pytest.raises(requests.Timeout):

        scraper.fetch_company_name(1)

    assert cache.get("1") == (False, None)


def test_id_mismatch_not_cached(
    tmp_path,
    monkeypatch,
    scraper_factory,
):

    cache = CompanyCache(tmp_path / "cache.db")

    scraper = scraper_factory(cache)

    monkeypatch.setattr(
        scraper,
        "fetch",
        Mock(return_value=response(company_id=2)),
    )

    with pytest.raises(
        ValueError,
        match="Company ID mismatch",
    ):

        scraper.fetch_company_name(1)

    assert cache.get("1") == (False, None)


def test_corrupted_cache_fallback(
    tmp_path,
    monkeypatch,
    scraper_factory,
):

    path = tmp_path / "cache.db"

    path.write_bytes(b"invalid sqlite database")

    cache = CompanyCache(path)

    scraper = scraper_factory(cache)

    fetch = Mock(return_value=response())

    monkeypatch.setattr(scraper, "fetch", fetch)

    assert scraper.fetch_company_name(1) == "Example Company"

    fetch.assert_called_once()

    assert cache.get("1") == (False, None)


def test_unavailable_directory(tmp_path):

    path = tmp_path / "not_directory"

    path.write_text("file")

    cache = CompanyCache(path / "cache.db")

    assert cache.get("1") == (False, None)

    assert not cache.put("1", "Company")


def test_disabled_configuration(monkeypatch):

    monkeypatch.setenv(
        "MATCHPOINT_COMPANY_CACHE",
        "0",
    )

    assert create_egyincs_company_cache() is None


def test_configured_path(tmp_path, monkeypatch):

    path = tmp_path / "configured.sqlite3"

    monkeypatch.setenv(
        "MATCHPOINT_COMPANY_CACHE",
        "1",
    )

    monkeypatch.setenv(
        "MATCHPOINT_COMPANY_CACHE_PATH",
        str(path),
    )

    cache = create_egyincs_company_cache()

    assert cache.path == path
    assert path.is_file()


def test_invalid_configuration(monkeypatch):

    monkeypatch.setenv(
        "MATCHPOINT_COMPANY_CACHE",
        "invalid",
    )

    with pytest.raises(ValueError):

        create_egyincs_company_cache()


@pytest.mark.parametrize(
    "enabled",
    ["0", "1"],
)
def test_cli_factory_activation(
    tmp_path,
    monkeypatch,
    enabled,
):

    from types import SimpleNamespace
    from scrapers.main import create_scraper

    path = tmp_path / "factory.sqlite3"

    monkeypatch.setenv(
        "MATCHPOINT_COMPANY_CACHE",
        enabled,
    )

    monkeypatch.setenv(
        "MATCHPOINT_COMPANY_CACHE_PATH",
        str(path),
    )

    args = SimpleNamespace(
        source="egyincs",
        max_jobs=1,
        max_pages=1,
        page_size=1,
        endpoint="jobs",
        load_strategy="bounded",
    )

    scraper = create_scraper(args, "api")

    try:

        if enabled == "1":

            assert isinstance(
                scraper.persistent_company_cache,
                CompanyCache,
            )

            assert scraper.persistent_company_cache.path == path

        else:

            assert scraper.persistent_company_cache is None

            assert not path.exists()

    finally:

        scraper.client.close()
