from abc import ABC, abstractmethod
from uuid import uuid4

from scrapers.models import Opportunity
from scrapers.source_config import get_source_config
from scrapers.utils.invalid_records import InvalidRecord
from scrapers.utils.http_client import HTTPClient
from scrapers.utils.logger import get_logger


class BaseScraper(ABC):

    def __init__(self, source_name: str):

        self.source_name = source_name
        self.source_config = get_source_config(source_name)
        self.logger = get_logger(source_name)
        self.client = HTTPClient(self.source_config)
    @abstractmethod
    def scrape(self) -> list[Opportunity]:
        pass

    def record_invalid(
        self,
        raw_payload: dict,
        error_type: str,
        error_message: str,
        source_url: str | None = None
    ) -> None:

        record = InvalidRecord(
            run_id=self.run_id,
            source_name=self.source_name,
            source_url=source_url,
            raw_payload=raw_payload,
            error_type=error_type,
            error_message=error_message
        )

        self.invalid_records.append(record)

        self.logger.warning(
            f"Invalid record | "
            f"Run ID: {self.run_id} | "
            f"Error: {error_type}"
        )

    def run(self) -> list[Opportunity]:

        self.run_id = str(uuid4())
        self.invalid_records: list[InvalidRecord] = []

        self.logger.info(
            f"Scraper started | Run ID: {self.run_id}"
        )
        try:

            opportunities = self.scrape()

            self.logger.info(
                f"Collected {len(opportunities)} opportunities | Run ID: {self.run_id}"            )
            self.logger.info(
                f"Rejected {len(self.invalid_records)} records | "
                f"Run ID: {self.run_id}"
            )

            return opportunities

        except Exception:

            self.logger.exception(
                f"Scraper failed | Run ID: {self.run_id}"
            )
            raise

        finally:

            self.client.close()

            self.logger.info(
                f"Scraper finished | Run ID: {self.run_id}"
            )