
import pytest

from bs4 import BeautifulSoup

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from scrapers.sources.forasna import ForasnaScraper

from test_forasna import (
    SEARCH,
    NEXT,
    job_url,
    search_html,
    detail_html,
    make_scraper,
)


def add_card(html, card):

    soup = BeautifulSoup(html, "lxml")

    container = soup.select_one(
        "#search-results-container"
    )

    fragment = BeautifulSoup(card, "html.parser")

    container.append(fragment)

    return str(soup)


INVALID_CARDS = [
    """
    <div class="result-wrp">
        <h2 class="job-title">
            <a href="https://example.com/job/2">
                External job
            </a>
        </h2>
    </div>
    """,
    """
    <div class="result-wrp">
        <h2 class="job-title">
            <a>Missing href</a>
        </h2>
    </div>
    """,
    """
    <div class="result-wrp">
        <h2 class="job-title">
            <a href="">Empty href</a>
        </h2>
    </div>
    """,
    """
    <div class="result-wrp">
        <h2 class="job-title">
            Missing anchor
        </h2>
    </div>
    """,
    """
    <div class="result-wrp">
        Missing title
    </div>
    """,
]


@pytest.mark.parametrize("card", INVALID_CARDS)
def test_mixed_valid_and_invalid_links(card):

    html = add_card(
        search_html([1]),
        card,
    )

    scraper = make_scraper({
        SEARCH: html,
        job_url(1): detail_html(1),
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0
    assert not result.scope_completed
    assert not result.source_exhausted

    assert scraper.stats["invalid_links"] == 1


def test_invalid_links_do_not_stop_pagination():

    html = add_card(
        search_html([1], NEXT),
        INVALID_CARDS[0],
    )

    scraper = make_scraper({
        SEARCH: html,
        NEXT: search_html([2]),
        job_url(1): detail_html(1),
        job_url(2): detail_html(2),
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 2
    assert scraper.stats["pages"] == 2
    assert scraper.stats["invalid_links"] == 1


def test_requested_limit_does_not_hide_extraction_issue():

    html = add_card(
        search_html([1]),
        INVALID_CARDS[0],
    )

    scraper = make_scraper(
        {
            SEARCH: html,
            job_url(1): detail_html(1),
        },
        max_jobs=1,
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1


def test_all_links_invalid():

    html = add_card(
        search_html([]),
        INVALID_CARDS[0],
    )

    scraper = make_scraper({
        SEARCH: html,
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 0
    assert scraper.stats["invalid_links"] == 1


def test_duplicate_links_are_not_invalid():

    soup = BeautifulSoup(
        search_html([1, 1, 2]),
        "lxml",
    )

    links, invalid_links = (
        ForasnaScraper.extract_job_links_with_diagnostics(
            soup
        )
    )

    assert list(links) == ["1", "2"]
    assert invalid_links == 0


def test_legacy_extraction_interface():

    soup = BeautifulSoup(
        add_card(
            search_html([1]),
            INVALID_CARDS[0],
        ),
        "lxml",
    )

    links = ForasnaScraper.extract_job_links(soup)

    assert isinstance(links, dict)
    assert links == {"1": job_url(1)}


def test_clean_collection_has_zero_invalid_links():

    scraper = make_scraper({
        SEARCH: search_html([1]),
        job_url(1): detail_html(1),
    })

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert scraper.stats["invalid_links"] == 0


def test_multiple_invalid_links_counted():

    html = search_html([1])

    for card in INVALID_CARDS:

        html = add_card(html, card)

    scraper = make_scraper({
        SEARCH: html,
        job_url(1): detail_html(1),
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.accepted_count == 1
    assert scraper.stats["invalid_links"] == len(
        INVALID_CARDS
    )
