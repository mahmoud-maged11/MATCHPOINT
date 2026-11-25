import json

from datetime import datetime, timezone

import pytest

from scrapers.sources.tanqeeb_mapper import TanqeebMapper
from scrapers.sources.tanqeeb_discovery import TanqeebDiscovery
from scrapers.sources.tanqeeb import TanqeebSource


BASE = "https://egypt.tanqeeb.com"

JOB_ID = "021458904"

JOB_URL = (
    BASE + f"/ar/jobs-in-egypt/all/jobs/{JOB_ID}.html"
)

OTHER_URL = (
    BASE + "/ar/jobs-in-middle-east/all/jobs/123456.html"
)

LISTING_URL = TanqeebDiscovery.LISTING_URL

OBSERVED_AT = datetime(
    2026, 11, 25, tzinfo=timezone.utc
)


def schema_html(data):

    return (
        '<script type="application/ld+json">'
        + json.dumps(data, ensure_ascii=False)
        + "</script>"
    )


def detail_html(**overrides):

    data = {
        "@type": "JobPosting",
        "title": "Data Engineer",
        "description": (
            "<p>Build data pipelines.</p>"
            "<strong>Qualifications</strong>"
            "<ul><li>Python</li><li>SQL</li></ul>"
        ),
        "hiringOrganization": {
            "name": "Test Company"
        },
        "jobLocation": {
            "address": {
                "addressLocality": "Cairo",
                "addressCountry": "EG"
            }
        },
        "employmentType": "FULL_TIME",
        "datePosted": "2026-11-20T10:00:00Z",
        "validThrough": "2026-12-20T10:00:00Z"
    }

    data.update(overrides)

    return schema_html(data)


def listing_html(urls, next_url=None):

    data = {
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "url": url
            }
            for index, url in enumerate(urls, 1)
        ]
    }

    html = schema_html(data)

    if next_url:
        html += f'<a href="{next_url}">التالي</a>'

    return html


def test_job_id_preserves_leading_zero():

    assert TanqeebMapper.extract_job_id(
        JOB_URL
    ) == JOB_ID


@pytest.mark.parametrize("url", [
    OTHER_URL,
    "https://example.com/jobs/123.html",
    "http://egypt.tanqeeb.com/ar/jobs-in-egypt/all/jobs/123.html",
    BASE + "/ar/jobs-in-egypt/all/jobs/abc.html"
])
def test_invalid_job_urls(url):

    with pytest.raises(ValueError):
        TanqeebMapper.extract_job_id(url)


def test_mapper_fields():

    result = TanqeebMapper.map_job(
        JOB_URL,
        detail_html(),
        OBSERVED_AT
    )

    assert result.source_name == "tanqeeb"
    assert result.source_opportunity_id == JOB_ID
    assert result.title == "Data Engineer"
    assert result.organization == "Test Company"
    assert result.location == "Cairo, Egypt"
    assert result.employment_types == ["full_time"]
    assert result.requirements == "Python\nSQL"
    assert result.published_at_precision == "exact"
    assert result.deadline_precision == "exact"
    assert result.status == "unknown"


def test_invalid_description():

    result = TanqeebMapper.map_job(
        JOB_URL,
        detail_html(description="e"),
        OBSERVED_AT
    )

    assert result.description is None
    assert result.requirements is None
    assert result.raw_payload["description_missing"]


def test_non_egypt_job():

    result = TanqeebMapper.map_job(
        JOB_URL,
        detail_html(
            jobLocation={
                "address": {
                    "addressCountry": "SA"
                }
            }
        ),
        OBSERVED_AT
    )

    assert result is None


def test_expired_job():

    result = TanqeebMapper.map_job(
        JOB_URL,
        detail_html(
            validThrough="2026-11-21T10:00:00Z"
        ),
        OBSERVED_AT
    )

    assert result.status == "expired"


def test_missing_job_posting():

    with pytest.raises(ValueError):
        TanqeebMapper.map_job(JOB_URL, "<html></html>")


def test_discovery_filters_and_deduplicates():

    urls, stats = TanqeebDiscovery.parse_listing(
        listing_html([JOB_URL, OTHER_URL, JOB_URL])
    )

    assert urls == [JOB_URL]
    assert stats["discovered"] == 3
    assert stats["non_egypt"] == 1
    assert stats["duplicates"] == 1
    assert stats["egypt_jobs"] == 1


def test_next_page():

    next_url = LISTING_URL + "/page/2"

    result = TanqeebDiscovery.extract_next_page(
        listing_html([JOB_URL], next_url),
        LISTING_URL
    )

    assert result == next_url


@pytest.mark.parametrize("next_url", [
    "https://example.com/page/2",
    LISTING_URL + "/page/5",
    LISTING_URL + "/page/2?countries[]=213",
    LISTING_URL + "/page/1"
])
def test_invalid_next_page(next_url):

    result = TanqeebDiscovery.extract_next_page(
        listing_html([JOB_URL], next_url),
        LISTING_URL
    )

    assert result is None


def test_collector_success():

    source = TanqeebSource(
        fetch_listing=lambda url: listing_html([JOB_URL]),
        fetch_detail=lambda url: detail_html()
    )

    results = source.run()

    assert len(results) == 1
    assert source.stats["pages_fetched"] == 1
    assert source.stats["details_fetched"] == 1
    assert source.stats["accepted"] == 1


def test_collector_missing_detail():

    source = TanqeebSource(
        fetch_listing=lambda url: listing_html([JOB_URL]),
        fetch_detail=lambda url: None
    )

    assert source.run() == []
    assert source.stats["details_missing"] == 1


def test_collector_invalid_record():

    source = TanqeebSource(
        fetch_listing=lambda url: listing_html([JOB_URL]),
        fetch_detail=lambda url: "<html></html>"
    )

    assert source.run() == []
    assert source.stats["invalid_records"] == 1
    assert len(source.invalid_records) == 1


def test_collector_page_limit():

    source = TanqeebSource(
        fetch_listing=lambda url: listing_html(
            [JOB_URL],
            LISTING_URL + "/page/2"
        ),
        fetch_detail=lambda url: detail_html(),
        max_pages=1
    )

    source.run()

    assert source.stats["pages_fetched"] == 1


@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_collection_limits(limit):

    with pytest.raises(ValueError):
        TanqeebSource(
            fetch_listing=lambda url: "",
            fetch_detail=lambda url: "",
            max_jobs=limit
        )

def test_canonical_validation():

    html = detail_html() + (
        f'<link rel="canonical" href="{JOB_URL}">'
    )

    result = TanqeebMapper.map_job(
        JOB_URL, html, OBSERVED_AT
    )

    assert result.raw_payload["canonical_verified"]
    assert str(result.source_url) == JOB_URL


def test_canonical_id_mismatch():

    other_job = JOB_URL.replace(JOB_ID, "999999")

    html = detail_html() + (
        f'<link rel="canonical" href="{other_job}">'
    )

    with pytest.raises(
        ValueError,
        match="Canonical job ID mismatch"
    ):
        TanqeebMapper.map_job(
            JOB_URL, html, OBSERVED_AT
        )


def test_missing_canonical():

    result = TanqeebMapper.map_job(
        JOB_URL, detail_html(), OBSERVED_AT
    )

    assert not result.raw_payload["canonical_verified"]


@pytest.mark.parametrize("tag, expected", [
    ("في المكتب", "on_site"),
    ("عن بعد", "remote"),
    ("هجين", "hybrid")
])
def test_html_work_modes(tag, expected):

    html = detail_html() + (
        '<div class="job-tags">'
        f'<span class="job-tag">{tag}</span>'
        '</div>'
    )

    result = TanqeebMapper.map_job(
        JOB_URL, html, OBSERVED_AT
    )

    assert result.work_modes == [expected]


def test_structured_remote():

    result = TanqeebMapper.map_job(
        JOB_URL,
        detail_html(jobLocationType="TELECOMMUTE"),
        OBSERVED_AT
    )

    assert result.work_modes == ["remote"]


def test_metadata_extraction():

    html = detail_html() + """
    <div class="meta">
        <span class="text-secondary">التصنيف</span>
        <span class="text-dark">خدمة العملاء</span>
    </div>

    <div class="meta">
        <span class="text-secondary">المجال</span>
        <span class="text-dark">مرافق الخدمات</span>
    </div>
    """

    result = TanqeebMapper.map_job(
        JOB_URL, html, OBSERVED_AT
    )

    assert result.categories == [
        "خدمة العملاء",
        "مرافق الخدمات"
    ]

    assert result.raw_payload["category"] == "خدمة العملاء"
    assert result.raw_payload["industry"] == "مرافق الخدمات"


def test_duplicate_categories():

    html = detail_html() + """
    <div class="meta">
        <span class="text-secondary">التصنيف</span>
        <span class="text-dark">أخرى</span>
    </div>

    <div class="meta">
        <span class="text-secondary">المجال</span>
        <span class="text-dark">أخرى</span>
    </div>
    """

    result = TanqeebMapper.map_job(
        JOB_URL, html, OBSERVED_AT
    )

    assert result.categories == ["أخرى"]


def test_search_options_are_not_categories():

    html = detail_html() + """
    <select>
        <option>خدمة العملاء</option>
        <option>تكنولوجيا المعلومات</option>
    </select>
    """

    result = TanqeebMapper.map_job(
        JOB_URL, html, OBSERVED_AT
    )

    assert result.categories is None


def test_apply_button_does_not_imply_active():

    html = detail_html() + (
        '<a class="apply-btn">تقدم للوظيفة</a>'
    )

    result = TanqeebMapper.map_job(
        JOB_URL, html, OBSERVED_AT
    )

    assert result.raw_payload["apply_button_present"]
    assert result.status == "unknown"


from scrapers.sources.tanqeeb_offline import TanqeebOfflineSource


def test_offline_source(tmp_path):

    listing_path = tmp_path / "egypt_page_1.html"

    listing_path.write_text(
        listing_html([JOB_URL]),
        encoding="utf-8"
    )

    detail_path = tmp_path / "detail_1.html"

    detail_path.write_text(
        detail_html() + (
            f'<link rel="canonical" href="{JOB_URL}">'
        ),
        encoding="utf-8"
    )

    source = TanqeebOfflineSource(
        listings_dir=tmp_path,
        max_pages=1
    )

    results = source.run()

    assert len(results) == 1
    assert results[0].source_opportunity_id == JOB_ID
    assert source.stats["accepted"] == 1


def test_offline_missing_directory(tmp_path):

    with pytest.raises(FileNotFoundError):

        TanqeebOfflineSource(
            listings_dir=tmp_path / "missing"
        )


def test_offline_missing_detail(tmp_path):

    (tmp_path / "egypt_page_1.html").write_text(
        listing_html([JOB_URL]),
        encoding="utf-8"
    )

    source = TanqeebOfflineSource(
        listings_dir=tmp_path,
        max_pages=1
    )

    assert source.run() == []
    assert source.stats["details_missing"] == 1


def test_offline_invalid_canonical(tmp_path):

    (tmp_path / "detail_1.html").write_text(
        detail_html() + (
            '<link rel="canonical" href="https://example.com">'
        ),
        encoding="utf-8"
    )

    source = TanqeebOfflineSource(
        listings_dir=tmp_path
    )

    assert source.details == {}