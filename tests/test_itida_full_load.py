
import pytest

from unittest.mock import Mock

from bs4 import BeautifulSoup

from scrapers.sources.itida import ITIDAScraper
from scrapers.sources.itida_mapper import ITIDAMapper
from scrapers.collection_result import StopReason

from test_itida import (
    scraper,
    configure_fetch,
    make_event_listing,
    make_program_listing,
)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_jobs": True},
        {"max_pages": False},
        {"max_jobs": 1.5},
        {"max_pages": "10"},
    ],
)
def test_strict_limit_validation(kwargs):

    with pytest.raises(ValueError):
        ITIDAScraper(**kwargs)


def test_unlimited_constructor():

    instance = ITIDAScraper(
        max_jobs=None,
        max_pages=None,
    )

    try:
        assert instance.max_jobs is None
        assert instance.max_pages is None
    finally:
        instance.client.close()


def test_full_load_exhaustion(scraper):

    scraper.max_jobs = None
    scraper.max_pages = None

    configure_fetch(
        scraper,
        event_listing=make_event_listing(
            slugs=("sample-event", "second-event"),
            next_page=2,
        ),
    )

    scraper.client.post.return_value = Mock(
        url=scraper.EVENTS_URL,
        text=make_event_listing(
            slugs=("third-event",),
        ),
    )

    result = scraper.run_with_result()

    assert result.source_exhausted
    assert result.accepted_count == 4
    assert result.rejected_count == 0
    assert scraper.stats["event_pages"] == 2
    assert scraper.stats["programs"] == 1
    assert scraper.stats["events"] == 3

    scraper.client.post.assert_called_once()


def test_full_load_overlap_is_partial(scraper):

    scraper.max_jobs = None
    scraper.max_pages = None

    configure_fetch(
        scraper,
        event_listing=make_event_listing(
            slugs=("sample-event", "second-event"),
            next_page=2,
        ),
    )

    scraper.client.post.return_value = Mock(
        url=scraper.EVENTS_URL,
        text=make_event_listing(
            slugs=("second-event", "third-event"),
        ),
    )

    result = scraper.run_with_result()

    assert result.status.value == "partial"
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 4
    assert scraper.stats["pagination_overlaps"] == 1

    ids = [
        row.source_opportunity_id
        for row in result.opportunities
    ]

    assert len(ids) == len(set(ids))


def test_full_load_repeated_page(scraper):

    scraper.max_jobs = None
    scraper.max_pages = None

    configure_fetch(
        scraper,
        event_listing=make_event_listing(
            next_page=2,
        ),
    )

    scraper.client.post.return_value = Mock(
        url=scraper.EVENTS_URL,
        text=make_event_listing(),
    )

    result = scraper.run_with_result()

    assert result.status.value == "partial"
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 2


def test_unsupported_program_diagnostics():

    links, unsupported = (
        ITIDAScraper.extract_program_links_with_diagnostics(
            make_program_listing()
        )
    )

    assert len(links) == 1
    assert unsupported == ["unknown"]

    assert links == ITIDAScraper.extract_program_links(
        make_program_listing()
    )


def test_program_diagnostics_in_collection(scraper):

    configure_fetch(scraper)

    result = scraper.run_with_result()

    assert result.source_exhausted

    assert scraper.stats["unsupported_programs"] == [
        "unknown"
    ]


def test_section_deduplication_order():

    soup = BeautifulSoup(
        """
        <main>
            <div class="ms-rtestate-field">First</div>
            <div class="ms-rtestate-field">Second</div>
            <div class="ms-rtestate-field">First</div>
            <div class="ms-rtestate-field">Third</div>
            <div class="ms-rtestate-field">Second</div>
        </main>
        """,
        "lxml",
    )

    assert ITIDAMapper.extract_program_sections(
        soup
    ) == ["First", "Second", "Third"]
