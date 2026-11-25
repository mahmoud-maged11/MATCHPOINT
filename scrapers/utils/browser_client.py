from playwright.sync_api import sync_playwright

from scrapers.source_config import SourceConfig
from scrapers.utils.logger import get_logger
from scrapers.utils.rate_limiter import RateLimiter


class BrowserClient:

    def __init__(self, source_config: SourceConfig):

        self.source_config = source_config

        self.logger = get_logger("browser_client")

        self.rate_limiter = RateLimiter(
            source_config.request_delay
        )

    def get_html(self, url: str) -> str:

        if not self.source_config.enabled:
            raise PermissionError(
                "Live collection is disabled for this source"
            )

        self.rate_limiter.wait()

        self.logger.info(f"Opening browser: {url}")

        with sync_playwright() as playwright:

            browser = playwright.chromium.launch(
                headless=True
            )

            try:

                page = browser.new_page()

                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.source_config.request_timeout * 1000
                )

                if response is None:
                    raise RuntimeError(
                        "No HTTP response received"
                    )

                if response.status >= 400:
                    raise RuntimeError(
                        f"HTTP error: {response.status}"
                    )

                html = page.content()

                self.logger.info(
                    f"Page loaded successfully: {response.status}"
                )

                return html

            finally:

                browser.close()