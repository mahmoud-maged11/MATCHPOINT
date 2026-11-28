
import json

import pytest
import requests

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from test_bayt import (
    scraper,
    setup_responses,
    make_response,
    make_listing,
    make_detail,
    job_url,
    LISTING,
    ROBOTS,
)


def configure(scraper, ids=(101,), next_page=None):

    pages = {
        LISTING: make_response(
            LISTING,
            make_listing(ids, next_page),
        ),
    }

    for job_id in ids:

        url = job_url(job_id)

        pages[url] = make_response(
            url, make_detail()
        )

    setup_responses(scraper, pages)


def override_response(scraper, url, value):

    original_get = scraper.client.get.side_effect

    def get(target, **kwargs):

        if target == url:

            if isinstance(value, Exception):
                raise value

            value.raise_for_status()

            return value

        return original_get(target, **kwargs)

    scraper.client.get.side_effect = get


def test_source_exhausted(scraper):

    configure(scraper)

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 1


@pytest.mark.parametrize(
    "attribute",
    ["max_jobs", "max_pages"],
)
def test_requested_limit(scraper, attribute):

    configure(scraper, next_page=2)

    setattr(scraper, attribute, 1)

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert result.accepted_count == 1
    assert not result.source_exhausted


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("Unavailable"),
        requests.Timeout("Timeout"),
        PermissionError("Access denied"),
    ],
)
def test_listing_failure_preserves_results(scraper, error):

    configure(scraper, next_page=2)

    override_response(
        scraper,
        LISTING + "?page=2",
        error,
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0


@pytest.mark.parametrize("status", [403, 429, 503])
def test_detail_failure_preserves_results(scraper, status):

    configure(scraper, ids=(101, 102))

    override_response(
        scraper,
        job_url(102),
        make_response(job_url(102), "", status),
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0


def test_empty_first_page_classification(scraper):

    setup_responses(
        scraper,
        {
            LISTING: make_response(
                LISTING, "<html></html>"
            ),
        },
    )

    with pytest.raises(ValueError):

        scraper.run_with_result()

    assert scraper.last_result.status == CollectionStatus.FAILED
    assert scraper.last_result.stop_reason == StopReason.PARSING_ERROR


def test_empty_second_page_preserves_results(scraper):

    configure(scraper, next_page=2)

    page2 = LISTING + "?page=2"

    override_response(
        scraper,
        page2,
        make_response(page2, "<html></html>"),
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1


def test_repeated_page_is_not_exhaustion(scraper):

    configure(scraper, next_page=2)

    page2 = LISTING + "?page=2"

    override_response(
        scraper,
        page2,
        make_response(page2, make_listing([101])),
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert scraper.stats["repeated_pages"] == 1
    assert scraper.stats["details_fetched"] == 1


@pytest.mark.parametrize(
    "link",
    [
        '<a data-js-aid="jobID">Missing URL</a>',
        '<a data-js-aid="jobID" href="">Empty URL</a>',
        (
            '<a data-js-aid="jobID" '
            'href="https://example.com/job-102/">'
            'External</a>'
        ),
    ],
)
def test_invalid_listing_links(scraper, link):

    configure(scraper)

    html = make_listing([101]) + f"<h2>{link}</h2>"

    override_response(
        scraper,
        LISTING,
        make_response(LISTING, html),
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1
    assert scraper.stats["invalid_listing_links"] == 1


@pytest.mark.parametrize(
    "link",
    [
        '<a rel="next">Missing URL</a>',
        '<a rel="next" href="">Empty URL</a>',
        '<a rel="next" href="https://example.com/">External</a>',
        f'<a class="jsAjaxLoad" href="{LISTING}?page=5">Wrong page</a>',
    ],
)
def test_invalid_pagination_is_not_exhaustion(scraper, link):

    configure(scraper)

    html = make_listing([101]) + link

    override_response(
        scraper,
        LISTING,
        make_response(LISTING, html),
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1
    assert scraper.stats["invalid_pagination_links"] == 1


def test_invalid_itemlist_entries(scraper):

    configure(scraper)

    data = {
        "@type": "ItemList",
        "itemListElement": [
            {"url": job_url(101)},
            {},
            "invalid",
        ],
    }

    html = make_listing([101]) + (
        '<script type="application/ld+json">'
        + json.dumps(data)
        + '</script>'
    )

    override_response(
        scraper,
        LISTING,
        make_response(LISTING, html),
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.accepted_count == 1
    assert scraper.stats["invalid_listing_links"] == 2


def test_invalid_identity_can_be_reprocessed(scraper):

    configure(scraper, ids=(101, 102), next_page=2)

    page2 = LISTING + "?page=2"

    override_response(
        scraper,
        page2,
        make_response(
            page2, make_listing([101, 103])
        ),
    )

    override_response(
        scraper,
        job_url(103),
        make_response(job_url(103), make_detail()),
    )

    original_get = scraper.client.get.side_effect
    attempts = 0

    def get(url, **kwargs):

        nonlocal attempts

        if url == job_url(101):

            attempts += 1

            return make_response(
                url,
                "<html></html>"
                if attempts == 1
                else make_detail(),
            )

        return original_get(url, **kwargs)

    scraper.client.get.side_effect = get

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 3
    assert result.rejected_count == 1
    assert attempts == 2


@pytest.mark.parametrize("status", [404, 410])
def test_unavailable_job_is_not_source_failure(scraper, status):

    configure(scraper, ids=(101, 102))

    override_response(
        scraper,
        job_url(102),
        make_response(job_url(102), "", status),
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 1
    assert result.rejected_count == 0
    assert scraper.stats["unavailable"] == 1


def test_non_egypt_filter_preserved(scraper):

    configure(scraper)

    override_response(
        scraper,
        job_url(101),
        make_response(
            job_url(101),
            make_detail(country="SA"),
        ),
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 0
    assert scraper.stats["non_egypt"] == 1


def test_robots_failure_classification(scraper):

    setup_responses(
        scraper,
        {},
        robots=(
            "User-agent: *"
            + chr(10)
            + "Disallow: /en/egypt/jobs/"
        ),
    )

    with pytest.raises(PermissionError):

        scraper.run_with_result()

    assert scraper.last_result.status == CollectionStatus.FAILED
    assert scraper.last_result.stop_reason == StopReason.SOURCE_ERROR

    scraper.client.get.assert_called_once()


def test_unexpected_error_propagates(scraper):

    configure(scraper)

    override_response(
        scraper,
        job_url(101),
        RuntimeError("Programming error"),
    )

    with pytest.raises(RuntimeError):

        scraper.run_with_result()

    scraper.client.close.assert_called_once()
