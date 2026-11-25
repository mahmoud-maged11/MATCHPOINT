import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scrapers.config import (
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    REQUEST_DELAY
)

from scrapers.source_config import SourceConfig
from scrapers.utils.logger import get_logger
from scrapers.utils.rate_limiter import RateLimiter


class HTTPClient:

    def __init__(self, source_config: SourceConfig | None = None):

        self.source_config = source_config

        self.request_timeout = (
            source_config.request_timeout
            if source_config is not None
            else REQUEST_TIMEOUT
        )

        self.max_retries = (
            source_config.max_retries
            if source_config is not None
            else MAX_RETRIES
        )

        self.request_delay = (
            source_config.request_delay
            if source_config is not None
            else REQUEST_DELAY
        )

        self.rate_limiter = RateLimiter(self.request_delay)

        self.logger = get_logger("http_client")

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": "MATCHPOINT/1.0"
        })

        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            respect_retry_after_header=True
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy
        )

        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get(self, url: str, params: dict | None = None):

        if (
            self.source_config is not None
            and not self.source_config.enabled
        ):
            raise PermissionError(
                "Live collection is disabled for this source"
            )

        self.logger.info(f"Requesting: {url}")

        try:

            self.rate_limiter.wait()

            response = self.session.get(
                url,
                params=params,
                timeout=self.request_timeout
            )

            response.raise_for_status()

            self.logger.info(
                f"Request successful: {response.status_code}"
            )

            return response

        except requests.RequestException as error:

            self.logger.error(
                f"Request failed: {error}"
            )

            raise

    def close(self):

        self.session.close()