from datetime import datetime, timezone

import pytest

from scrapers.sources.bayt import BaytScraper
from scrapers.sources.bayt_mapper import BaytMapper


BASE = "https://www.bayt.com"
JOB_ID = "75503203"
JOB_URL = f"{BASE}/en/egypt/jobs/test-job-{JOB_ID}/"


def fallback_html():

    return f"""
    <html>
    <head>
        <link rel="canonical" href="{JOB_URL}">
    </head>
    <body>
        <div>
            <h1 id="job_title" data-jb-field="title">
                Data Engineer
            </h1>
            <a href="/en/company/example/">
                Example Company
            </a>
        </div>

        <span class="jb-label-location">
            Cairo, Egypt
        </span>

        <a id="applyLink_1"
           href="/en/job/apply/index/{JOB_ID}/">
            Apply on company site
        </a>
    </body>
    </html>
    """


def test_verified_html_fallback():

    observed_at = datetime(
        2026, 11, 28, 8, 0,
        tzinfo=timezone.utc
    )

    result = BaytMapper.map_job(
        JOB_URL,
        fallback_html(),
        observed_at=observed_at,
    )

    assert result.source_opportunity_id == JOB_ID
    assert result.title == "Data Engineer"
    assert result.organization == "Example Company"
    assert result.location == "Cairo, Egypt"
    assert result.description is None
    assert result.published_at is None
    assert result.deadline is None
    assert result.status == "active"
    assert result.collected_at == observed_at

    assert (
        result.raw_payload["mapping_evidence"]
        == "verified_html"
    )


@pytest.mark.parametrize(
    "original,replacement",
    [
        (
            JOB_URL,
            f"{BASE}/en/egypt/jobs/other-job-99999/",
        ),
        (
            f"/en/job/apply/index/{JOB_ID}/",
            "/en/job/apply/index/99999/",
        ),
        (
            "Cairo, Egypt",
            "Dubai, UAE",
        ),
        (
            'data-jb-field="title"',
            'data-jb-field="unrelated"',
        ),
    ],
)
def test_fallback_rejects_unverified_evidence(
    original,
    replacement,
):

    html = fallback_html().replace(
        original, replacement
    )

    with pytest.raises(ValueError):
        BaytMapper.map_job(JOB_URL, html)


def test_fallback_rejects_ambiguous_jsonld():

    html = fallback_html() + """
    <script type="application/ld+json">
    [
        {"@type": "JobPosting", "title": "First"},
        {"@type": "JobPosting", "title": "Second"}
    ]
    </script>
    """

    with pytest.raises(ValueError):
        BaytMapper.map_job(JOB_URL, html)


def test_pagination_ignores_other_valid_pages():

    html = """
    <a class="jsAjaxLoad"
       href="/en/egypt/jobs/">1</a>

    <a class="jsAjaxLoad"
       href="/en/egypt/jobs/?page=2">2</a>

    <a class="jsAjaxLoad"
       href="/en/egypt/jobs/?page=4">4</a>

    <a class="jsAjaxLoad"
       href="/en/egypt/jobs/?page=5">5</a>

    <a class="jsAjaxLoad"
       href="/en/company/example/">Company</a>
    """

    next_url, invalid = (
        BaytScraper.extract_next_page_with_diagnostics(
            html, 3
        )
    )

    assert next_url == (
        BASE + "/en/egypt/jobs/?page=4"
    )

    assert invalid == 0


def test_last_page_with_previous_navigation():

    html = """
    <a class="jsAjaxLoad"
       href="/en/egypt/jobs/?page=170">170</a>

    <a class="jsAjaxLoad"
       href="/en/egypt/jobs/?page=171">171</a>
    """

    next_url, invalid = (
        BaytScraper.extract_next_page_with_diagnostics(
            html, 172
        )
    )

    assert next_url is None
    assert invalid == 0


@pytest.mark.parametrize(
    "href",
    [
        "https://example.com/en/egypt/jobs/?page=4",
        "/en/egypt/jobs/?page=abc",
        "/en/egypt/jobs/?page=7",
        "/en/egypt/jobs/?page=2",
        "",
    ],
)
def test_invalid_explicit_next_link(href):

    html = f'<a rel="next" href="{href}">Next</a>'

    next_url, invalid = (
        BaytScraper.extract_next_page_with_diagnostics(
            html, 3
        )
    )

    assert next_url is None
    assert invalid == 1


@pytest.mark.parametrize(
    "current_page,target_page",
    [
        (1, 5),
        (3, 5),
        (10, 15),
        (170, 172),
    ],
)
def test_future_page_without_immediate_next(
    current_page,
    target_page,
):

    html = (
        '<a class="jsAjaxLoad" '
        f'href="/en/egypt/jobs/?page={target_page}">'
        'Later page</a>'
    )

    next_url, invalid = (
        BaytScraper.extract_next_page_with_diagnostics(
            html,
            current_page,
        )
    )

    assert next_url is None
    assert invalid > 0
