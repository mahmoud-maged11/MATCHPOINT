from unittest.mock import Mock

import pytest

from scrapers.sources.bayt import (
    BaytScraper,
    UnsafeJobRedirect,
)

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from scrapers.sources.bayt_mapper import BaytMapper


BASE = "https://www.bayt.com"
JOB = BASE + "/en/egypt/jobs/old-title-12345/"
NEW_JOB = BASE + "/en/egypt/jobs/new-title-12345/"


def response(url, status=200, location=None):

    result = Mock()
    result.url = url
    result.status_code = status
    result.content = b"<html>Job details</html>"
    result.headers = {}

    if location is not None:
        result.headers["Location"] = location

    return result


@pytest.fixture
def scraper():

    instance = BaytScraper()

    instance.robots = Mock()
    instance.robots.can_fetch.return_value = True
    instance.client.get = Mock()

    yield instance

    instance.client.close()


def test_safe_same_identity_redirect(scraper):

    scraper.client.get.side_effect = [
        response(JOB, 302, NEW_JOB),
        response(NEW_JOB),
    ]

    assert scraper.fetch_html(JOB) == (
        "<html>Job details</html>"
    )

    assert scraper.client.get.call_count == 2

    for call in scraper.client.get.call_args_list:
        assert call.kwargs["allow_redirects"] is False


@pytest.mark.parametrize(
    "target",
    [
        BASE + "/en/egypt/jobs/other-job-99999/",
        "https://example.com/en/egypt/jobs/job-12345/",
        "http://www.bayt.com/en/egypt/jobs/job-12345/",
        BASE + "/en/egypt/jobs/",
        BASE + "/en/egypt/jobs/job-12345/?page=2",
        "",
    ],
)
def test_unsafe_redirect_not_followed(scraper, target):

    scraper.client.get.return_value = response(
        JOB, 302, target
    )

    with pytest.raises(UnsafeJobRedirect):
        scraper.fetch_html(JOB)

    assert scraper.client.get.call_count == 1


def test_redirect_loop_stops(scraper):

    scraper.client.get.return_value = response(
        JOB, 302, JOB
    )

    with pytest.raises(
        PermissionError,
        match="redirect loop",
    ):
        scraper.fetch_html(JOB)

    assert scraper.client.get.call_count == 1


def test_redirect_target_requires_robots_permission(scraper):

    scraper.client.get.return_value = response(
        JOB, 302, NEW_JOB
    )

    scraper.robots.can_fetch.side_effect = [
        True,
        False,
    ]

    with pytest.raises(
        PermissionError,
        match="Disallowed URL",
    ):
        scraper.fetch_html(JOB)

    assert scraper.client.get.call_count == 1


def test_listing_redirect_not_followed(scraper):

    listing = BaytScraper.LISTING_URL

    scraper.client.get.return_value = response(
        listing,
        302,
        listing + "?page=2",
    )

    with pytest.raises(
        PermissionError,
        match="Unexpected listing redirect",
    ):
        scraper.fetch_html(listing)

    assert scraper.client.get.call_count == 1


def test_direct_response_without_redirect(scraper):

    scraper.client.get.return_value = response(JOB)

    assert scraper.fetch_html(JOB) == (
        "<html>Job details</html>"
    )

    scraper.client.get.assert_called_once_with(
        JOB,
        allow_redirects=False,
    )


def test_redirect_limit(scraper):

    urls = [
        BASE + f"/en/egypt/jobs/title-{i}-12345/"
        for i in range(5)
    ]

    scraper.client.get.side_effect = [
        response(urls[i], 302, urls[i + 1])
        for i in range(4)
    ]

    with pytest.raises(
        PermissionError,
        match="redirect limit",
    ):
        scraper.fetch_html(urls[0])

    assert scraper.client.get.call_count == 4


def listing_html(ids):

    return "".join(
        f'<h2><a data-js-aid="jobID" '
        f'href="/en/egypt/jobs/job-{job_id}/">'
        f'Job {job_id}</a></h2>'
        for job_id in ids
    )


def valid_detail(job_id):

    return f"""
    <script type="application/ld+json">
    {{
        "@type": "JobPosting",
        "title": "Data Engineer",
        "hiringOrganization": {{
            "name": "Example Company"
        }},
        "jobLocation": {{
            "address": {{
                "addressCountry": "EG",
                "addressLocality": "Cairo"
            }}
        }}
    }}
    </script>
    """


def test_single_unsafe_redirect_isolated(scraper):

    scraper.load_robots = Mock()

    scraper.fetch_html = Mock(
        side_effect=[
            listing_html(["12345", "12346"]),
            UnsafeJobRedirect("Identity mismatch"),
            valid_detail("12346"),
        ]
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 1
    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR

    assert (
        result.opportunities[0].source_opportunity_id
        == "12346"
    )

    assert scraper.stats["unsafe_job_redirects"] == 1
    assert scraper.fetch_html.call_count == 3


def test_repeated_unsafe_redirects_stop_collection(scraper):

    scraper.load_robots = Mock()

    scraper.fetch_html = Mock(
        side_effect=[
            listing_html([
                "12345",
                "12346",
                "12347",
                "12348",
                "12349",
            ]),
            valid_detail("12345"),
            UnsafeJobRedirect("Unsafe target"),
            UnsafeJobRedirect("Unsafe target"),
            UnsafeJobRedirect("Unsafe target"),
            valid_detail("12349"),
        ]
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 1
    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert scraper.stats["unsafe_job_redirects"] == 3
    assert scraper.fetch_html.call_count == 5


def test_robots_denial_not_isolated(scraper):

    scraper.load_robots = Mock()

    scraper.fetch_html = Mock(
        side_effect=[
            listing_html(["12345", "12346", "12347"]),
            valid_detail("12345"),
            PermissionError("Disallowed URL"),
            valid_detail("12347"),
        ]
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 1
    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert scraper.stats["unsafe_job_redirects"] == 0
    assert scraper.fetch_html.call_count == 3
