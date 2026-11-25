
import json

from unittest.mock import Mock

import pytest
import requests

from scrapers.sources.bayt import BaytScraper


BASE = "https://www.bayt.com"
LISTING = BASE + "/en/egypt/jobs/"
ROBOTS = BASE + "/robots.txt"


def job_url(job_id):

    return LISTING + f"job-{job_id}/"


def make_response(url, body, status=200):

    response = requests.Response()

    response.url = url
    response.status_code = status
    response._content = body.encode("utf-8")
    response.encoding = "utf-8"

    return response


def make_listing(ids, next_page=None):

    links = []

    for job_id in ids:

        links.append(f"""
        <h2>
            <a data-js-aid="jobID"
               data-automation-is_aggregated="1"
               data-automation-is_external="0"
               href="{job_url(job_id)}">
               Job {job_id}
            </a>
        </h2>
        """)

    if next_page is not None:

        links.append(f"""
        <a class="jsAjaxLoad"
           href="{LISTING}?page={next_page}">
           More Results
        </a>
        """)

    return "<html>" + "".join(links) + "</html>"


def make_detail(
    title="Data Engineer",
    country="EG",
    apply=True,
):

    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "description": "<p>Build pipelines.</p>",
        "hiringOrganization": {
            "name": "Example Company",
        },
        "jobLocation": {
            "address": {
                "addressCountry": country,
                "addressLocality": "Cairo",
            }
        },
        "employmentType": "FULL_TIME",
    }

    button = (
        '<a id="applyLink_1">Easy Apply</a>'
        if apply else ""
    )

    return f"""
    <html>
        <script type="application/ld+json">
            {json.dumps(posting)}
        </script>
        {button}
    </html>
    """


@pytest.fixture
def scraper():

    instance = BaytScraper(
        max_jobs=20,
        max_pages=10,
    )

    instance.client.close()
    instance.client = Mock()

    yield instance

    instance.client.close()


def setup_responses(scraper, pages, robots=None):

    robots = robots or "User-agent: *\nDisallow:"

    responses = {
        ROBOTS: make_response(ROBOTS, robots),
    }

    responses.update(pages)

    def get(url, **kwargs):

        if url not in responses:
            raise AssertionError(
                f"Unexpected request: {url}"
            )

        response = responses[url]

        response.raise_for_status()

        return response

    scraper.client.get.side_effect = get


@pytest.mark.parametrize(
    "max_jobs,max_pages",
    [(0, 10), (20, 0), (-1, 10), (20, -1)],
)
def test_invalid_limits(max_jobs, max_pages):

    with pytest.raises(ValueError):

        BaytScraper(
            max_jobs=max_jobs,
            max_pages=max_pages,
        )


def test_html_discovery():

    jobs = BaytScraper.extract_jobs(
        make_listing([101, 102])
    )

    assert len(jobs) == 2
    assert jobs[0]["job_id"] == "101"
    assert jobs[0]["is_aggregated"] is True
    assert jobs[0]["is_external"] is False


def test_json_ld_discovery():

    data = {
        "@type": "ItemList",
        "itemListElement": [
            {"url": job_url(101)},
            {"url": job_url(102)},
        ],
    }

    html = f"""
    <script type="application/ld+json">
        {json.dumps(data)}
    </script>
    """

    jobs = BaytScraper.extract_jobs(html)

    assert len(jobs) == 2
    assert jobs[0]["is_aggregated"] is None


def test_discovery_deduplication():

    data = {
        "@type": "ItemList",
        "itemListElement": [
            {"url": job_url(101)},
            {"url": job_url(102)},
        ],
    }

    html = make_listing([101]) + f"""
    <script type="application/ld+json">
        {json.dumps(data)}
    </script>
    """

    jobs = BaytScraper.extract_jobs(html)

    assert len(jobs) == 2
    assert jobs[0]["is_aggregated"] is True


def test_invalid_links_ignored():

    html = """
    <h2>
        <a data-js-aid="jobID"
           href="https://example.com/job-101/">
           Invalid
        </a>
    </h2>
    <h2>
        <a data-js-aid="jobID"
           href="/en/uae/jobs/job-102/">
           Outside Egypt
        </a>
    </h2>
    """

    assert BaytScraper.extract_jobs(html) == []


def test_relative_arabic_job_link():

    html = """
    <h2>
        <a data-js-aid="jobID"
           href="/en/egypt/jobs/%D9%85-101/">
           Job
        </a>
    </h2>
    """

    jobs = BaytScraper.extract_jobs(html)

    assert jobs[0]["job_id"] == "101"


def test_invalid_json_ld_ignored():

    html = """
    <script type="application/ld+json">
        invalid json
    </script>
    """

    assert BaytScraper.extract_jobs(html) == []


def test_next_page():

    html = make_listing([101], next_page=2)

    assert BaytScraper.extract_next_page(
        html, 1
    ) == LISTING + "?page=2"


def test_no_next_page():

    assert BaytScraper.extract_next_page(
        make_listing([101]), 1
    ) is None


def test_skip_unexpected_next_page():

    assert BaytScraper.extract_next_page(
        make_listing([101], next_page=5), 1
    ) is None


def test_external_next_page():

    html = """
    <a class="jsAjaxLoad"
       href="https://example.com/en/egypt/jobs/?page=2">
       Next
    </a>
    """

    assert BaytScraper.extract_next_page(
        html, 1
    ) is None


@pytest.mark.parametrize(
    "url",
    [
        ROBOTS,
        LISTING,
        LISTING + "?page=2",
        job_url(101),
    ],
)
def test_valid_urls(url):

    BaytScraper.validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/en/egypt/jobs/",
        LISTING + "?page=0",
        LISTING + "?page=2&filter=1",
        LISTING + "?other=2",
        LISTING + "#fragment",
        "https://www.bayt.com/en/uae/jobs/",
    ],
)
def test_invalid_urls(url):

    with pytest.raises(ValueError):
        BaytScraper.validate_url(url)


def test_fetch_without_robots(scraper):

    with pytest.raises(PermissionError):
        scraper.fetch_html(LISTING)

    scraper.client.get.assert_not_called()


def test_robots_disallowed(scraper):

    setup_responses(
        scraper,
        {},
        robots=(
            "User-agent: *\n"
            "Disallow: /en/egypt/jobs/"
        ),
    )

    with pytest.raises(PermissionError):
        scraper.run()

    assert scraper.client.get.call_count == 1


def test_robots_unavailable(scraper):

    scraper.client.get.return_value = make_response(
        ROBOTS, "", 503
    )

    with pytest.raises(PermissionError):
        scraper.run()


def test_redirect_rejected(scraper):

    setup_responses(
        scraper,
        {
            LISTING: make_response(
                "https://example.com/",
                "<html></html>",
            )
        },
    )

    with pytest.raises(PermissionError):
        scraper.run()


def test_full_collection(scraper):

    page2 = LISTING + "?page=2"

    setup_responses(
        scraper,
        {
            LISTING: make_response(
                LISTING,
                make_listing([101, 102], 2),
            ),
            page2: make_response(
                page2,
                make_listing([102, 103]),
            ),
            job_url(101): make_response(
                job_url(101), make_detail()
            ),
            job_url(102): make_response(
                job_url(102), make_detail()
            ),
            job_url(103): make_response(
                job_url(103), make_detail()
            ),
        },
    )

    results = scraper.run()

    assert len(results) == 3
    assert scraper.stats["listing_pages"] == 2
    assert scraper.stats["duplicates"] == 1
    assert scraper.stats["details_fetched"] == 3
    assert scraper.stats["accepted"] == 3
    assert scraper.stats["active"] == 3
    assert scraper.stats["aggregated"] == 3
    assert scraper.stats["external"] == 0


def test_max_jobs(scraper):

    scraper.max_jobs = 1

    setup_responses(
        scraper,
        {
            LISTING: make_response(
                LISTING,
                make_listing([101, 102], 2),
            ),
            job_url(101): make_response(
                job_url(101), make_detail()
            ),
        },
    )

    assert len(scraper.run()) == 1
    assert scraper.stats["details_fetched"] == 1


def test_max_pages(scraper):

    scraper.max_pages = 1

    setup_responses(
        scraper,
        {
            LISTING: make_response(
                LISTING,
                make_listing([101], 2),
            ),
            job_url(101): make_response(
                job_url(101), make_detail()
            ),
        },
    )

    assert len(scraper.run()) == 1
    assert scraper.stats["listing_pages"] == 1


def test_non_egypt_skipped(scraper):

    setup_responses(
        scraper,
        {
            LISTING: make_response(
                LISTING, make_listing([101])
            ),
            job_url(101): make_response(
                job_url(101),
                make_detail(country="SA"),
            ),
        },
    )

    assert scraper.run() == []
    assert scraper.stats["non_egypt"] == 1


@pytest.mark.parametrize("status", [404, 410])
def test_unavailable_job(scraper, status):

    setup_responses(
        scraper,
        {
            LISTING: make_response(
                LISTING, make_listing([101])
            ),
            job_url(101): make_response(
                job_url(101), "", status
            ),
        },
    )

    assert scraper.run() == []
    assert scraper.stats["unavailable"] == 1


def test_invalid_record(scraper):

    setup_responses(
        scraper,
        {
            LISTING: make_response(
                LISTING, make_listing([101])
            ),
            job_url(101): make_response(
                job_url(101), "<html></html>"
            ),
        },
    )

    assert scraper.run() == []
    assert scraper.stats["invalid"] == 1
    assert len(scraper.invalid_records) == 1


def test_empty_listing_raises(scraper):

    setup_responses(
        scraper,
        {
            LISTING: make_response(
                LISTING, "<html></html>"
            ),
        },
    )

    with pytest.raises(ValueError):
        scraper.run()


@pytest.mark.parametrize("status", [403, 429, 503])
def test_http_error_propagates(scraper, status):

    setup_responses(
        scraper,
        {
            LISTING: make_response(
                LISTING, make_listing([101])
            ),
            job_url(101): make_response(
                job_url(101), "", status
            ),
        },
    )

    with pytest.raises(requests.HTTPError):
        scraper.run()


def test_unknown_status_retained(scraper):

    setup_responses(
        scraper,
        {
            LISTING: make_response(
                LISTING, make_listing([101])
            ),
            job_url(101): make_response(
                job_url(101),
                make_detail(apply=False),
            ),
        },
    )

    results = scraper.run()

    assert len(results) == 1
    assert results[0].status == "unknown"
    assert scraper.stats["unknown"] == 1
