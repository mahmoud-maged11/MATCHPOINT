
from unittest.mock import Mock

import pytest
import requests

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from test_itida import (
    scraper,
    configure_fetch,
    make_event_listing,
    make_event_detail,
    PROGRAM_URL,
    EVENT_URL,
)


def test_source_exhausted(scraper):

    configure_fetch(scraper)

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 2

    reports = scraper.stats["scope_results"]

    assert reports["programs"]["completed"]
    assert reports["events"]["completed"]


def test_job_limit(scraper):

    scraper.max_jobs = 1

    configure_fetch(scraper)

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert result.accepted_count == 1
    assert not result.source_exhausted


def test_page_limit(scraper):

    scraper.max_pages = 1

    configure_fetch(
        scraper,
        event_listing=make_event_listing(next_page=2),
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT

    scraper.client.post.assert_not_called()


def test_repeated_event_page(scraper):

    configure_fetch(
        scraper,
        event_listing=make_event_listing(next_page=2),
    )

    scraper.client.post.return_value = Mock(
        url=scraper.EVENTS_URL,
        text=make_event_listing(),
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 2


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("Connection lost"),
        requests.Timeout("Timeout"),
        PermissionError("Access denied"),
    ],
)
def test_event_listing_failure_preserves_programs(
    scraper, error
):

    configure_fetch(scraper)

    original_fetch = scraper.fetch_html.side_effect

    def fetch(url):

        if url == scraper.EVENTS_URL:
            raise error

        return original_fetch(url)

    scraper.fetch_html.side_effect = fetch

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1


def test_program_source_failure_stops_requests(scraper):

    configure_fetch(scraper)

    scraper.fetch_html.side_effect = (
        requests.ConnectionError("Unavailable")
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.SOURCE_ERROR

    scraper.fetch_html.assert_called_once_with(
        scraper.PROGRAMS_URL
    )


def test_program_parsing_failure_allows_events(scraper):

    configure_fetch(
        scraper,
        program_listing="<html></html>",
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1

    assert result.opportunities[0].source_opportunity_id == (
        "event:sample-event"
    )


def test_detail_failure_preserves_previous_results(scraper):

    configure_fetch(
        scraper,
        event_listing=make_event_listing(
            slugs=("sample-event", "second-event"),
        ),
    )

    original_fetch = scraper.fetch_html.side_effect

    def fetch(url):

        if url.endswith("/second-event.aspx"):

            raise requests.ConnectionError("Unavailable")

        return original_fetch(url)

    scraper.fetch_html.side_effect = fetch

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 2
    assert result.rejected_count == 0


def test_postback_failure_preserves_programs(scraper):

    configure_fetch(
        scraper,
        event_listing=make_event_listing(next_page=2),
    )

    scraper.client.post.side_effect = (
        requests.ConnectionError("PostBack failed")
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1

    scraper.client.post.assert_called_once()


def test_no_duplicate_pagination_check(scraper):

    configure_fetch(scraper)

    scraper.fetch_next_event_page = Mock(
        return_value=None
    )

    result = scraper.run_with_result()

    assert result.source_exhausted

    scraper.fetch_next_event_page.assert_called_once()


@pytest.mark.parametrize(
    "card",
    [
        '<h4 class="listingHeader">Missing link</h4>',
        '<h4 class="listingHeader"><a href="">Empty</a></h4>',
        (
            '<h4 class="listingHeader">'
            '<a href="https://example.com/event.aspx">'
            'External</a></h4>'
        ),
    ],
)
def test_mixed_valid_and_invalid_event_links(scraper, card):

    html = make_event_listing().replace(
        "</main>",
        card + "</main>",
    )

    configure_fetch(scraper, event_listing=html)

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 2
    assert scraper.stats["invalid_event_links"] == 1


def test_invalid_detail_is_rejected(scraper):

    configure_fetch(scraper)

    original_fetch = scraper.fetch_html.side_effect

    def fetch(url):

        if url == EVENT_URL:
            return "<html></html>"

        return original_fetch(url)

    scraper.fetch_html.side_effect = fetch

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 1
    assert result.rejected_count == 1


def test_robots_failure_stops_collection(scraper):

    scraper.load_robots.side_effect = PermissionError(
        "Access denied"
    )

    with pytest.raises(PermissionError):

        scraper.run_with_result()

    assert scraper.last_result.status == CollectionStatus.FAILED

    assert scraper.last_result.stop_reason == (
        StopReason.SOURCE_ERROR
    )

    scraper.client.close.assert_called_once()


def test_unexpected_error_propagates(scraper):

    configure_fetch(scraper)

    scraper.fetch_html.side_effect = RuntimeError(
        "Programming error"
    )

    with pytest.raises(RuntimeError):

        scraper.run_with_result()

    scraper.client.close.assert_called_once()
