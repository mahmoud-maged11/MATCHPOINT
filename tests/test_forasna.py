import json

from unittest.mock import Mock

import pytest
import requests

from bs4 import BeautifulSoup

from scrapers.sources.forasna import ForasnaScraper


BASE = "https://forasna.com"

SEARCH = BASE + "/وظائف-خالية"

NEXT = SEARCH + "?start=20"


def job_url(job_id):

    return f"{BASE}/job/p/test-job-{job_id}"


def search_html(ids, next_url=None):

    cards = "".join(
        f"""
        <div class="result-wrp">
            <h2 class="job-title">
                <a href="{job_url(job_id)}">Job</a>
            </h2>
        </div>
        """
        for job_id in ids
    )

    pagination = (
        f'<link rel="next" href="{next_url}">'
        if next_url else ""
    )

    return f"""
    <html>
        <head>{pagination}</head>
        <div id="search-results-container">
            {cards}
        </div>
    </html>
    """


def detail_html(job_id, country="EG", active=True,
                deadline="2099-12-25T09:00:00+02:00"):

    posting = {
        "@type": "JobPosting",
        "identifier": {
            "value": str(job_id)
        },
        "title": f"Job {job_id}",
        "employmentType": "FULL_TIME",
        "validThrough": deadline,
        "jobLocation": {
            "address": {
                "addressCountry": country
            }
        }
    }

    button = (
        '<a class="apply-btn">تقدم للوظيفة</a>'
        if active else ""
    )

    return f"""
    <html>
        <script type="application/ld+json">
            {json.dumps(posting)}
        </script>
        {button}
    </html>
    """


def make_scraper(pages, max_jobs=20, max_pages=10):

    scraper = ForasnaScraper(
        max_jobs=max_jobs,
        max_pages=max_pages
    )

    scraper.client.close()
    scraper.client = Mock()

    def fake_get(url):

        if url == BASE + "/robots.txt":
            return Mock(
                text="User-agent: *\nDisallow:",
                url=url
            )

        value = pages[url]

        if isinstance(value, Exception):
            raise value

        return Mock(text=value, url=url)

    scraper.client.get.side_effect = fake_get

    return scraper


def test_extract_links():

    soup = BeautifulSoup(
        search_html([1, 2, 2]),
        "lxml"
    )

    links = ForasnaScraper.extract_job_links(soup)

    assert list(links) == ["1", "2"]


def test_extract_next_page():

    soup = BeautifulSoup(
        search_html([1], NEXT),
        "lxml"
    )

    assert ForasnaScraper.extract_next_page(soup) == NEXT


def test_external_pagination_rejected():

    soup = BeautifulSoup(
        search_html([1], "https://example.com"),
        "lxml"
    )

    with pytest.raises(ValueError):
        ForasnaScraper.extract_next_page(soup)


def test_collect_multiple_pages():

    scraper = make_scraper({
        SEARCH: search_html([1, 2], NEXT),
        NEXT: search_html([3]),
        job_url(1): detail_html(1),
        job_url(2): detail_html(2),
        job_url(3): detail_html(3)
    })

    results = scraper.run()

    assert len(results) == 3
    assert scraper.stats["pages"] == 2
    assert scraper.stats["accepted"] == 3


def test_duplicate_jobs():

    scraper = make_scraper({
        SEARCH: search_html([1], NEXT),
        NEXT: search_html([1, 2]),
        job_url(1): detail_html(1),
        job_url(2): detail_html(2)
    })

    results = scraper.run()

    assert len(results) == 2
    assert scraper.stats["duplicates"] == 1


def test_max_jobs():

    scraper = make_scraper(
        {
            SEARCH: search_html([1, 2]),
            job_url(1): detail_html(1)
        },
        max_jobs=1
    )

    assert len(scraper.run()) == 1
    assert scraper.stats["details_fetched"] == 1


def test_max_pages():

    scraper = make_scraper(
        {
            SEARCH: search_html([1], NEXT),
            job_url(1): detail_html(1)
        },
        max_pages=1
    )

    assert len(scraper.run()) == 1
    assert scraper.stats["pages"] == 1


def test_non_egyptian_job():

    scraper = make_scraper({
        SEARCH: search_html([1, 2]),
        job_url(1): detail_html(1, country="SA"),
        job_url(2): detail_html(2)
    })

    assert len(scraper.run()) == 1
    assert scraper.stats["non_egyptian"] == 1


def test_missing_country():

    scraper = make_scraper({
        SEARCH: search_html([1]),
        job_url(1): detail_html(1, country=None)
    })

    assert scraper.run() == []
    assert scraper.stats["non_egyptian"] == 1


def test_expired_job():

    scraper = make_scraper({
        SEARCH: search_html([1]),
        job_url(1): detail_html(
            1,
            deadline="2020-01-01T00:00:00+02:00"
        )
    })

    assert scraper.run() == []
    assert scraper.stats["expired"] == 1


def test_inactive_job():

    scraper = make_scraper({
        SEARCH: search_html([1]),
        job_url(1): detail_html(1, active=False)
    })

    assert scraper.run() == []
    assert scraper.stats["inactive"] == 1


def test_invalid_job():

    scraper = make_scraper({
        SEARCH: search_html([1, 2]),
        job_url(1): "<html></html>",
        job_url(2): detail_html(2)
    })

    assert len(scraper.run()) == 1
    assert scraper.stats["invalid"] == 1
    assert len(scraper.invalid_records) == 1


def test_unavailable_job():

    response = requests.Response()
    response.status_code = 404

    error = requests.HTTPError(response=response)

    scraper = make_scraper({
        SEARCH: search_html([1, 2]),
        job_url(1): error,
        job_url(2): detail_html(2)
    })

    assert len(scraper.run()) == 1
    assert scraper.stats["unavailable"] == 1


def test_http_403_propagates():

    response = requests.Response()
    response.status_code = 403

    scraper = make_scraper({
        SEARCH: search_html([1]),
        job_url(1): requests.HTTPError(
            response=response
        )
    })

    with pytest.raises(requests.HTTPError):
        scraper.run()


def test_robots_disallowed():

    scraper = ForasnaScraper()

    scraper.client.close()
    scraper.client = Mock()

    scraper.client.get.return_value = Mock(
        text="User-agent: *\nDisallow: /",
        url=BASE + "/robots.txt"
    )

    with pytest.raises(PermissionError):
        scraper.run()


def test_invalid_limits():

    with pytest.raises(ValueError):
        ForasnaScraper(max_jobs=0)

    with pytest.raises(ValueError):
        ForasnaScraper(max_pages=0)