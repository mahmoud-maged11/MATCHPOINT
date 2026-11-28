
import pytest
import requests

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from test_nti import (
    scraper,
    configure_live_mock,
    make_response,
    make_http_error,
    make_courses,
    make_discovery,
    DETAIL_HTML,
)


def override_response(scraper, suffix, value):

    original_get = scraper.client.get.side_effect

    def fake_get(url, **kwargs):

        if url.endswith(suffix):

            if isinstance(value, Exception):
                raise value

            return make_response(url, value)

        return original_get(url, **kwargs)

    scraper.client.get.side_effect = fake_get


def test_source_exhausted(scraper):

    configure_live_mock(scraper)

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 3

    for report in scraper.stats["initiative_results"].values():

        assert report["stop_reason"] == "source_exhausted"
        assert report["processed"] == report["discovered"]


@pytest.mark.parametrize(
    "attribute,limit,expected",
    [
        ("max_jobs", 2, 2),
        ("max_pages", 1, 1),
    ],
)
def test_requested_limits(scraper, attribute, limit, expected):

    configure_live_mock(scraper)

    setattr(scraper, attribute, limit)

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert result.accepted_count == expected
    assert not result.source_exhausted


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("Connection lost"),
        requests.Timeout("Timeout"),
        PermissionError("Access denied"),
    ],
)
def test_listing_failure_preserves_results(scraper, error):

    configure_live_mock(scraper)

    override_response(
        scraper,
        "coursesev.php?catID=202",
        error,
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0


def test_detail_failure_preserves_results(scraper):

    configure_live_mock(scraper)

    override_response(
        scraper,
        "/2581.html",
        requests.ConnectionError("Unavailable"),
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.accepted_count == 1
    assert result.stop_reason == StopReason.SOURCE_ERROR


def test_discovery_failure_stops_requests(scraper):

    configure_live_mock(scraper)

    override_response(
        scraper,
        "/dey/catev.php",
        make_http_error(403),
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 0

    assert scraper.client.get.call_count == 3


def test_invalid_discovery_preserves_other_initiatives(scraper):

    configure_live_mock(scraper)

    override_response(
        scraper,
        "/dey/catev.php",
        "<html></html>",
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 2


def test_mixed_discovery_links(scraper):

    configure_live_mock(scraper)

    html = make_discovery(
        "coursesev.php", "catID", "202", "AI"
    )

    html += """
    <div class="trackLinks">
        <a href="https://example.com">Invalid</a>
    </div>
    """

    override_response(
        scraper,
        "/dey/catev.php",
        html,
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.accepted_count == 3
    assert result.stop_reason == StopReason.PARSING_ERROR

    assert scraper.stats["invalid_discovery_links"] == 1


def test_mixed_course_links(scraper):

    configure_live_mock(scraper)

    override_response(
        scraper,
        "coursesev.php?catID=202",
        make_courses(("2581", "abc", "0")),
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.accepted_count == 3
    assert result.stop_reason == StopReason.PARSING_ERROR

    assert scraper.stats["invalid_course_links"] == 2


def test_missing_course_target(scraper):

    configure_live_mock(scraper)

    html = make_courses(("2581",))

    html = html.replace(
        "</div>",
        "</div>",
    )

    html += """
    <div class="courseLinks">
        <a href="javascript:;">Missing target</a>
    </div>
    """

    override_response(
        scraper,
        "coursesev.php?catID=202",
        html,
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.accepted_count == 3
    assert scraper.stats["invalid_course_links"] == 1


def test_empty_listing_is_not_exhaustion(scraper):

    configure_live_mock(scraper)

    override_response(
        scraper,
        "coursesev.php?catID=202",
        "<html></html>",
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 2


@pytest.mark.parametrize("status", [404, 410])
def test_unavailable_course_is_not_collection_failure(
    scraper, status
):

    configure_live_mock(scraper)

    override_response(
        scraper,
        "/2581.html",
        make_http_error(status),
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 2
    assert scraper.stats["unavailable"] == 1


def test_missing_shared_career_module_is_source_failure(scraper):

    configure_live_mock(scraper)

    override_response(
        scraper,
        "/careerDev4m.html",
        make_http_error(404),
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert scraper.stats["unavailable"] == 0


def test_invalid_identity_can_be_retried(scraper):

    configure_live_mock(scraper)

    override_response(
        scraper,
        "coursesev.php?catID=202",
        make_courses(("2581", "2581")),
    )

    original_get = scraper.client.get.side_effect
    attempts = 0

    def fake_get(url, **kwargs):

        nonlocal attempts

        if url.endswith("/2581.html"):

            attempts += 1

            html = (
                "<p>Invalid detail</p>"
                if attempts == 1
                else DETAIL_HTML
            )

            return make_response(url, html)

        return original_get(url, **kwargs)

    scraper.client.get.side_effect = fake_get

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 3
    assert result.rejected_count == 1
    assert attempts == 2


def test_robots_failure_classification(scraper):

    scraper.client.get.side_effect = make_http_error(403)

    with pytest.raises(requests.HTTPError):

        scraper.run_with_result()

    assert scraper.last_result.status == CollectionStatus.FAILED
    assert scraper.last_result.stop_reason == StopReason.SOURCE_ERROR


def test_unexpected_error_propagates(scraper):

    configure_live_mock(scraper)

    override_response(
        scraper,
        "/2581.html",
        RuntimeError("Programming error"),
    )

    with pytest.raises(RuntimeError):

        scraper.run_with_result()

    scraper.client.close.assert_called_once()
