
from unittest.mock import Mock
from urllib.robotparser import RobotFileParser

import pytest
import requests

from scrapers.sources.nti import NTIScraper


BASE_URL = NTIScraper.BASE_URL

DETAIL_HTML = """
<h1>Sample Course (72 Hours)</h1>
<h3>Module Description</h3>
<ul><li>Technical training.</li></ul>
<h3>Module Prerequisite</h3>
<ul><li>Basic Computer Skills.</li></ul>
"""

CAREER_HTML = """
<h2>Part 2: Career development - Duration: 126 Hours.</h2>
<h3>Overview:</h3>
<ul><li>Career development.</li></ul>
"""


def make_response(url, html="", status=200):

    response = Mock()
    response.url = url
    response.status_code = status
    response.text = html
    response.content = html.encode("utf-8")

    return response


def make_http_error(status):

    response = requests.Response()
    response.status_code = status

    return requests.HTTPError(
        f"HTTP {status}",
        response=response,
    )


def make_discovery(endpoint, parameter, page_id, label):

    return f"""
    <div class="trackLinks">
        <a href="{endpoint}?{parameter}={page_id}">
            {label}
        </a>
    </div>
    """


def make_courses(track_ids=("2581",), closed=False):

    links = []

    for track_id in track_ids:

        status = (
            '<span class="closed">'
            'Registration closed for this track'
            '</span>'
            if closed else ""
        )

        links.append(
            f'<a href="javascript:;" data-target="{track_id}">'
            f'<div>Course {track_id}</div>{status}</a>'
        )

    return (
        '<div class="courseLinks">'
        + "".join(links)
        + '</div>'
    )


def make_page(**overrides):

    page = {
        "page_id": "202",
        "label": "AI and IoT",
        "url": BASE_URL + "/dey/coursesev.php?catID=202",
    }

    page.update(overrides)

    return page


@pytest.fixture
def scraper():

    instance = NTIScraper(max_jobs=10, max_pages=3)

    instance.client.close()
    instance.client = Mock()

    instance.robots = RobotFileParser()
    instance.robots.parse([
        "User-agent: *",
        "Disallow:",
    ])

    instance.stats = {
        "robots_status": None,
        "cache_hits": 0,
        "details_fetched": 0,
        "career_details_fetched": 0,
        "unavailable": 0,
        "invalid": 0,
        "accepted": 0,
        "closed": 0,
        "unknown": 0,
        "hire_ready": 0,
        "upskilling": 0,
        "creativa": 0,
    }

    yield instance

    instance.client.close()


def configure_live_mock(scraper):

    responses = {
        "/robots.txt": "User-agent: *\nDisallow:",

        "/dey/cat4m.php": make_discovery(
            "courses4m.php", "catID", "304", "DevOps"
        ),

        "/dey/catev.php": make_discovery(
            "coursesev.php", "catID", "202", "AI"
        ),

        "/dey/catcrloc.php": make_discovery(
            "coursescrloc.php", "centerID", "13", "Giza"
        ),

        "/dey/courses4m.php?catID=304": make_courses(
            ("5301",), closed=True
        ),

        "/dey/coursesev.php?catID=202": make_courses(
            ("2581",), closed=True
        ),

        "/dey/coursescrloc.php?centerID=13": make_courses(
            ("8102",)
        ),

        "/dey/pages/modules/careerDev4m.html": CAREER_HTML,
    }

    def fake_get(url, **kwargs):

        path = url.removeprefix(BASE_URL)

        if path in responses:
            return make_response(url, responses[path])

        if path.startswith("/dey/pages/modules/"):
            return make_response(url, DETAIL_HTML)

        raise AssertionError(f"Unexpected URL: {url}")

    scraper.client.get.side_effect = fake_get


def test_category_discovery():

    html = make_discovery(
        "coursesev.php", "catID", "202", "AI"
    )

    pages = NTIScraper.extract_listing_pages(
        html,
        BASE_URL + "/dey/catev.php",
        "coursesev.php",
        "catID",
    )

    assert len(pages) == 1
    assert pages[0]["page_id"] == "202"
    assert pages[0]["label"] == "AI"


def test_center_discovery():

    html = make_discovery(
        "coursescrloc.php", "centerID", "13", "Giza"
    )

    pages = NTIScraper.extract_listing_pages(
        html,
        BASE_URL + "/dey/catcrloc.php",
        "coursescrloc.php",
        "centerID",
    )

    assert len(pages) == 1
    assert pages[0]["page_id"] == "13"
    assert pages[0]["label"] == "Giza"


def test_duplicate_listing_pages():

    html = make_discovery(
        "coursesev.php", "catID", "202", "AI"
    ) * 2

    pages = NTIScraper.extract_listing_pages(
        html,
        BASE_URL + "/dey/catev.php",
        "coursesev.php",
        "catID",
    )

    assert len(pages) == 1


def test_external_listing_ignored():

    html = """
    <div class="trackLinks">
        <a href="https://example.com/dey/coursesev.php?catID=202">
            External
        </a>
    </div>
    """

    pages = NTIScraper.extract_listing_pages(
        html,
        BASE_URL + "/dey/catev.php",
        "coursesev.php",
        "catID",
    )

    assert pages == []


def test_closed_course_extraction():

    courses = NTIScraper.extract_courses(
        make_courses(closed=True),
        "upskilling",
        make_page(),
    )

    assert len(courses) == 1
    assert courses[0]["track_id"] == "2581"
    assert courses[0]["closed"] is True
    assert courses[0]["title"] == "Course 2581"


def test_unknown_course_extraction():

    courses = NTIScraper.extract_courses(
        make_courses(),
        "upskilling",
        make_page(),
    )

    assert courses[0]["closed"] is False
    assert courses[0]["status_raw"] is None


def test_creativa_location():

    courses = NTIScraper.extract_courses(
        make_courses(("8102",)),
        "creativa",
        make_page(page_id="13", label="Giza"),
    )

    assert courses[0]["center_id"] == "13"
    assert courses[0]["location"] == "Giza"
    assert courses[0]["category"] is None


def test_invalid_track_ids_ignored():

    courses = NTIScraper.extract_courses(
        make_courses(("0", "abc", "-1", "2581")),
        "upskilling",
        make_page(),
    )

    assert len(courses) == 1
    assert courses[0]["track_id"] == "2581"


def test_detail_cache(scraper):

    scraper.fetch_html = Mock(return_value=DETAIL_HTML)

    first = scraper.fetch_detail("2581")
    second = scraper.fetch_detail("2581")

    assert first == second
    assert scraper.fetch_html.call_count == 1
    assert scraper.stats["cache_hits"] == 1
    assert scraper.stats["details_fetched"] == 1


def test_career_cache(scraper):

    scraper.fetch_html = Mock(return_value=CAREER_HTML)

    scraper.fetch_career_details()
    scraper.fetch_career_details()

    assert scraper.fetch_html.call_count == 1
    assert scraper.stats["career_details_fetched"] == 1


@pytest.mark.parametrize("status", [404, 410])
def test_missing_robots_policy(scraper, status):

    scraper.client.get.side_effect = make_http_error(status)

    scraper.load_robots()

    assert scraper.stats["robots_status"] == status

    assert scraper.robots.can_fetch(
        scraper.USER_AGENT, BASE_URL + "/dey/catev.php"
    )


@pytest.mark.parametrize("status", [403, 429, 500, 503])
def test_robots_failure_stops_collection(scraper, status):

    scraper.client.get.side_effect = make_http_error(status)

    with pytest.raises(requests.HTTPError):
        scraper.load_robots()


def test_robots_denied(scraper):

    scraper.robots = RobotFileParser()
    scraper.robots.parse([
        "User-agent: *",
        "Disallow: /dey/",
    ])

    with pytest.raises(PermissionError):

        scraper.fetch_html(
            BASE_URL + "/dey/catev.php"
        )

    scraper.client.get.assert_not_called()


def test_redirect_rejected(scraper):

    scraper.client.get.return_value = make_response(
        BASE_URL + "/different.html",
        DETAIL_HTML,
    )

    with pytest.raises(PermissionError):

        scraper.fetch_html(
            BASE_URL + "/dey/catev.php"
        )


def test_utf8_decoding(scraper):

    url = BASE_URL + "/dey/catev.php"

    scraper.client.get.return_value = make_response(
        url, "<h1>التدريب الصيفي</h1>"
    )

    assert "التدريب الصيفي" in scraper.fetch_html(url)


def test_full_collection(scraper):

    configure_live_mock(scraper)

    results = scraper.run()

    assert len(results) == 3
    assert scraper.stats["accepted"] == 3
    assert scraper.stats["closed"] == 2
    assert scraper.stats["unknown"] == 1
    assert scraper.stats["discovery_pages"] == 3
    assert scraper.stats["listing_pages"] == 3
    assert scraper.stats["details_fetched"] == 3
    assert scraper.stats["career_details_fetched"] == 1

    assert len({
        item.source_opportunity_id for item in results
    }) == 3


def test_max_jobs(scraper):

    configure_live_mock(scraper)

    scraper.max_jobs = 2

    results = scraper.run()

    assert len(results) == 2


def test_max_pages(scraper):

    configure_live_mock(scraper)

    scraper.max_pages = 1

    results = scraper.run()

    assert len(results) == 1
    assert scraper.stats["listing_pages"] == 1


def test_duplicate_courses(scraper):

    configure_live_mock(scraper)

    original_get = scraper.client.get.side_effect

    def fake_get(url, **kwargs):

        if url.endswith("courses4m.php?catID=304"):

            return make_response(
                url,
                make_courses(("5301", "5301"), closed=True),
            )

        return original_get(url, **kwargs)

    scraper.client.get.side_effect = fake_get

    results = scraper.run()

    assert len(results) == 3
    assert scraper.stats["duplicates"] == 1


def test_unavailable_detail(scraper):

    configure_live_mock(scraper)

    original_get = scraper.client.get.side_effect

    def fake_get(url, **kwargs):

        if url.endswith("/2581.html"):
            raise make_http_error(404)

        return original_get(url, **kwargs)

    scraper.client.get.side_effect = fake_get

    results = scraper.run()

    assert len(results) == 2
    assert scraper.stats["unavailable"] == 1


def test_invalid_detail_recorded(scraper):

    configure_live_mock(scraper)

    original_get = scraper.client.get.side_effect

    def fake_get(url, **kwargs):

        if url.endswith("/2581.html"):

            return make_response(
                url, "<p>Invalid module</p>"
            )

        return original_get(url, **kwargs)

    scraper.client.get.side_effect = fake_get

    results = scraper.run()

    assert len(results) == 2
    assert scraper.stats["invalid"] == 1
    assert len(scraper.invalid_records) == 1


@pytest.mark.parametrize(
    "max_jobs,max_pages",
    [(0, 10), (-1, 10), (20, 0), (20, -1)],
)
def test_invalid_limits(max_jobs, max_pages):

    with pytest.raises(ValueError):

        NTIScraper(
            max_jobs=max_jobs,
            max_pages=max_pages,
        )
