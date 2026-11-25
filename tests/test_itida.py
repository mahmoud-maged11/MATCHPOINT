import pytest
import requests

from bs4 import BeautifulSoup
from unittest.mock import Mock
from urllib.robotparser import RobotFileParser

from scrapers.sources.itida import ITIDAScraper


BASE = "https://itida.gov.eg"

PROGRAM_URL = (
    BASE + "/English/Programs/"
    "StudentSummerTraining/Pages/default.aspx"
)

EVENT_URL = (
    BASE + "/English/MediaCenter/"
    "Events/Pages/sample-event.aspx"
)

TARGET = "ctl00$sample$_aspNetContentPager"


def make_program_listing():

    return f"""
    <main>
        <a href="{PROGRAM_URL}">Summer Training</a>
        <a href="{PROGRAM_URL}?tracking=1">Duplicate</a>

        <a href="/English/Programs/Unknown/Pages/default.aspx">
            Unsupported program
        </a>

        <a href="https://example.com/page.aspx">
            External link
        </a>
    </main>
    """


def make_program_detail():

    return """
    <main>
        <h1 class="briefHeader">Summer Training</h1>

        <div class="ms-rtestate-field">
            Training for students.
        </div>
    </main>
    """


def make_event_detail():

    return """
    <main>
        <div class="EventItemDev">
            <h4>AI Workshop</h4>

            <div>Start Date: 20/11/2026</div>
            <div>End Date: 21/11/2026</div>
            <div>Location: Cairo</div>
            <div>Category: Workshop</div>
        </div>

        <div class="innerPageContent">
            Learn AI.
        </div>
    </main>
    """


def make_event_listing(
    slugs=("sample-event",),
    next_page=None,
    viewstate="state1"
):

    cards = "".join(
        f"""
        <h4 class="listingHeader">
            <a href="/English/MediaCenter/Events/Pages/{slug}.aspx">
                {slug}
            </a>
        </h4>
        """
        for slug in slugs
    )

    pagination = ""

    if next_page is not None:

        pagination = f"""
        <a class="AspNetPagerPagingButtonsClass"
           href="javascript:__doPostBack('{TARGET}','{next_page}')">
            {next_page}
        </a>
        """

    return f"""
    <html>
        <form id="aspnetForm" method="post"
              action="{ITIDAScraper.EVENTS_URL}">

            <input type="hidden" name="__VIEWSTATE"
                   value="{viewstate}">

            <input type="hidden" name="__EVENTVALIDATION"
                   value="validation">

            <input type="hidden" name="__EVENTTARGET"
                   value="">

            <input type="hidden" name="__EVENTARGUMENT"
                   value="">

            <main>
                {cards}
                {pagination}
            </main>

        </form>
    </html>
    """


@pytest.fixture
def scraper():

    instance = ITIDAScraper(
        max_jobs=4,
        max_pages=3
    )

    instance.client.close()

    instance.client = Mock()

    instance.robots = RobotFileParser()

    instance.robots.parse([
        "User-agent: *",
        "Disallow:"
    ])

    instance.load_robots = Mock()

    yield instance

    instance.client.close()


def configure_fetch(
    scraper,
    event_listing=None,
    program_listing=None
):

    pages = {
        scraper.PROGRAMS_URL: (
            program_listing
            if program_listing is not None
            else make_program_listing()
        ),

        scraper.EVENTS_URL: (
            event_listing
            if event_listing is not None
            else make_event_listing()
        ),

        PROGRAM_URL: make_program_detail(),
        EVENT_URL: make_event_detail()
    }

    def fetch(url):

        if url in pages:
            return pages[url]

        if "/Events/Pages/" in url:
            return make_event_detail()

        raise ValueError(f"Unexpected URL: {url}")

    scraper.fetch_html = Mock(side_effect=fetch)


def test_program_link_discovery():

    links = ITIDAScraper.extract_program_links(
        make_program_listing()
    )

    assert links == [PROGRAM_URL]


def test_event_link_discovery():

    soup = BeautifulSoup(
        make_event_listing(),
        "lxml"
    )

    links = ITIDAScraper.extract_event_links(soup)

    assert links == [EVENT_URL]


def test_duplicate_event_links():

    soup = BeautifulSoup(
        make_event_listing(
            slugs=("sample-event", "sample-event")
        ),
        "lxml"
    )

    assert ITIDAScraper.extract_event_links(soup) == [
        EVENT_URL
    ]


def test_postback_extraction():

    soup = BeautifulSoup(
        make_event_listing(next_page=2),
        "lxml"
    )

    assert ITIDAScraper.extract_postback(
        soup, 2
    ) == (TARGET, "2")


def test_missing_postback():

    soup = BeautifulSoup(
        make_event_listing(),
        "lxml"
    )

    assert ITIDAScraper.extract_postback(
        soup, 2
    ) is None


def test_form_extraction():

    soup = BeautifulSoup(
        make_event_listing(),
        "lxml"
    )

    payload = ITIDAScraper.extract_form(soup)

    assert payload["__VIEWSTATE"] == "state1"
    assert payload["__EVENTVALIDATION"] == "validation"


def test_external_form_action_rejected():

    html = make_event_listing().replace(
        ITIDAScraper.EVENTS_URL,
        "https://example.com"
    )

    soup = BeautifulSoup(html, "lxml")

    with pytest.raises(ValueError):

        ITIDAScraper.extract_form(soup)


def test_missing_viewstate():

    html = make_event_listing().replace(
        "__VIEWSTATE",
        "invalid_field"
    )

    soup = BeautifulSoup(html, "lxml")

    with pytest.raises(ValueError):

        ITIDAScraper.extract_form(soup)


def test_postback_request(scraper):

    soup = BeautifulSoup(
        make_event_listing(next_page=2),
        "lxml"
    )

    scraper.client.post.return_value = Mock(
        url=scraper.EVENTS_URL,
        text=make_event_listing(
            slugs=("second-event",),
            viewstate="state2"
        )
    )

    result = scraper.fetch_next_event_page(
        soup, 2
    )

    payload = (
        scraper.client.post.call_args.kwargs["data"]
    )

    assert payload["__EVENTTARGET"] == TARGET
    assert payload["__EVENTARGUMENT"] == "2"
    assert payload["__VIEWSTATE"] == "state1"

    assert len(
        scraper.extract_event_links(result)
    ) == 1


def test_collect_program_and_event(scraper):

    configure_fetch(scraper)

    results = scraper.run()

    assert len(results) == 2

    assert scraper.stats["programs"] == 1
    assert scraper.stats["events"] == 1
    assert scraper.stats["accepted"] == 2


def test_collect_multiple_event_pages(scraper):

    configure_fetch(
        scraper,
        event_listing=make_event_listing(
            next_page=2
        )
    )

    scraper.client.post.return_value = Mock(
        url=scraper.EVENTS_URL,
        text=make_event_listing(
            slugs=("second-event", "third-event")
        )
    )

    results = scraper.run()

    assert len(results) == 4
    assert scraper.stats["event_pages"] == 2

    scraper.client.post.assert_called_once()


def test_max_jobs_limit(scraper):

    scraper.max_jobs = 1

    configure_fetch(scraper)

    results = scraper.run()

    assert len(results) == 1
    assert scraper.stats["programs"] == 0
    assert scraper.stats["events"] == 1


def test_max_pages_limit(scraper):

    scraper.max_pages = 1

    configure_fetch(
        scraper,
        event_listing=make_event_listing(
            next_page=2
        )
    )

    results = scraper.run()

    assert len(results) == 2
    assert scraper.stats["event_pages"] == 1

    scraper.client.post.assert_not_called()


def test_repeated_event_page(scraper):

    configure_fetch(
        scraper,
        event_listing=make_event_listing(
            next_page=2
        )
    )

    scraper.client.post.return_value = Mock(
        url=scraper.EVENTS_URL,
        text=make_event_listing()
    )

    results = scraper.run()

    assert len(results) == 2
    assert scraper.stats["duplicates"] == 1


def test_historical_events_retained(scraper):

    configure_fetch(scraper)

    results = scraper.run()

    events = [
        result for result in results
        if result.source_opportunity_id.startswith("event:")
    ]

    assert len(events) == 1
    assert events[0].status == "expired"


def test_invalid_detail_record(scraper):

    configure_fetch(scraper)

    original_fetch = scraper.fetch_html.side_effect

    def fetch(url):

        if url == EVENT_URL:
            return "<html></html>"

        return original_fetch(url)

    scraper.fetch_html.side_effect = fetch

    results = scraper.run()

    assert len(results) == 1
    assert scraper.stats["invalid"] == 1
    assert len(scraper.invalid_records) == 1


def test_unavailable_detail(scraper):

    configure_fetch(scraper)

    original_fetch = scraper.fetch_html.side_effect

    def fetch(url):

        if url == EVENT_URL:

            response = requests.Response()
            response.status_code = 404

            raise requests.HTTPError(
                "Not found",
                response=response
            )

        return original_fetch(url)

    scraper.fetch_html.side_effect = fetch

    results = scraper.run()

    assert len(results) == 1
    assert scraper.stats["unavailable"] == 1


def test_robots_denied(scraper):

    scraper.robots = RobotFileParser()

    scraper.robots.parse([
        "User-agent: *",
        "Disallow: /English/"
    ])

    with pytest.raises(PermissionError):

        scraper.check_access(EVENT_URL)

def test_empty_event_listing(scraper):

    configure_fetch(
        scraper,
        event_listing=make_event_listing(slugs=())
    )

    with pytest.raises(ValueError):

        scraper.run()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_jobs": 0},
        {"max_jobs": -1},
        {"max_pages": 0},
        {"max_pages": -1}
    ]
)
def test_invalid_configuration(kwargs):

    with pytest.raises(ValueError):

        ITIDAScraper(**kwargs)