import pytest

from unittest.mock import Mock, patch

from scrapers.source_config import SourceConfig
from scrapers.utils.browser_client import BrowserClient


@pytest.fixture
def browser_setup():

    with patch(
        "scrapers.utils.browser_client.sync_playwright"
    ) as mock_playwright:

        playwright = (
            mock_playwright.return_value
            .start.return_value
        )

        browser = playwright.chromium.launch.return_value

        page = browser.new_page.return_value

        page.goto.return_value.status = 200

        page.content.return_value = (
            "<html><body>Test Page</body></html>"
        )

        yield mock_playwright, browser, page


def test_browser_client_configuration():

    config = SourceConfig(
        base_url="https://example.com",
        request_timeout=60,
        request_delay=5,
        enabled=True
    )

    client = BrowserClient(config)

    assert client.source_config.request_timeout == 60

    assert client.rate_limiter.min_interval == 5


def test_disabled_source_blocks_browser():

    config = SourceConfig(
        base_url="https://example.com",
        enabled=False
    )

    client = BrowserClient(config)

    with patch(
        "scrapers.utils.browser_client.sync_playwright"
    ) as mock_playwright:

        with pytest.raises(PermissionError):

            client.get_html("https://example.com")

        mock_playwright.assert_not_called()


def test_browser_returns_html(browser_setup):

    _, browser, page = browser_setup

    config = SourceConfig(
        base_url="https://example.com",
        enabled=True
    )

    client = BrowserClient(config)

    html = client.get_html("https://example.com")

    assert html == "<html><body>Test Page</body></html>"

    page.content.assert_called_once()

    browser.close.assert_called_once()


def test_browser_request_timeout(browser_setup):

    _, _, page = browser_setup

    config = SourceConfig(
        base_url="https://example.com",
        request_timeout=60,
        enabled=True
    )

    client = BrowserClient(config)

    client.get_html("https://example.com")

    assert page.goto.call_args.kwargs["timeout"] == 60000


def test_browser_http_error(browser_setup):

    _, browser, page = browser_setup

    page.goto.return_value.status = 403

    config = SourceConfig(
        base_url="https://example.com",
        enabled=True
    )

    client = BrowserClient(config)

    with pytest.raises(RuntimeError, match="HTTP error: 403"):

        client.get_html("https://example.com")

    browser.close.assert_called_once()

    page.content.assert_not_called()


def test_browser_rate_limiter(browser_setup):

    config = SourceConfig(
        base_url="https://example.com",
        enabled=True
    )

    client = BrowserClient(config)

    client.rate_limiter.wait = Mock()

    client.get_html("https://example.com")

    client.rate_limiter.wait.assert_called_once()


def test_browser_missing_response(browser_setup):

    _, browser, page = browser_setup

    page.goto.return_value = None

    config = SourceConfig(
        base_url="https://example.com",
        enabled=True
    )

    client = BrowserClient(config)

    with pytest.raises(
        RuntimeError,
        match="No HTTP response received"
    ):

        client.get_html("https://example.com")

    browser.close.assert_called_once()