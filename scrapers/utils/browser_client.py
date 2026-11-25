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

        self._playwright = None
        self._browser = None
        self._page = None

    def start(self):

        if not self.source_config.enabled:
            raise PermissionError(
                "Live collection is disabled for this source"
            )

        if self._browser is not None:
            return

        try:

            self._playwright = sync_playwright().start()

            self._browser = self._playwright.chromium.launch(
                headless=True
            )

            self._page = self._browser.new_page()

        except Exception:

            self.close()
            raise

    def close(self):

        try:

            if self._browser is not None:
                self._browser.close()

        finally:

            try:

                if self._playwright is not None:
                    self._playwright.stop()

            finally:

                self._page = None
                self._browser = None
                self._playwright = None

    def __enter__(self):

        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):

        self.close()

    def get_html(self, url: str) -> str:

        if not self.source_config.enabled:
            raise PermissionError(
                "Live collection is disabled for this source"
            )

        temporary_session = self._browser is None

        try:

            self.start()

            self.rate_limiter.wait()

            self.logger.info(f"Opening page: {url}")

            response = self._page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.source_config.request_timeout * 1000
            )

            if response is None:
                raise RuntimeError(
                    "No HTTP response received"
                )

            if response.status != 200:
                raise RuntimeError(
                    f"HTTP error: {response.status}"
                )

            html = self._page.content()

            self.logger.info(
                f"Page loaded successfully: {response.status}"
            )

            return html

        finally:

            if temporary_session:
                self.close()