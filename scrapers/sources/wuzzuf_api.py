from datetime import datetime, timezone

import requests

from scrapers.base_scraper import BaseScraper
from scrapers.models import Opportunity
from scrapers.sources.wuzzuf_mapper import WuzzufMapper


class WuzzufAPIScraper(BaseScraper):

    def __init__(
        self,
        max_jobs: int = 20,
        page_size: int = 20,
        max_pages: int = 10
    ):

        super().__init__("wuzzuf")

        if max_jobs <= 0:
            raise ValueError("max_jobs must be positive")

        if not 1 <= page_size <= 20:
            raise ValueError("page_size must be 1-20")

        if max_pages <= 0:
            raise ValueError("max_pages must be positive")

        self.max_jobs = max_jobs
        self.page_size = page_size
        self.max_pages = max_pages

        self.base_url = self.source_config.base_url

        self.mapper = WuzzufMapper()

        self.company_cache: dict[str, str | None] = {}

        self.stats = {}

    def fetch_page(
        self,
        offset: int,
        limit: int
    ) -> list[dict]:

        response = self.client.get(
            f"{self.base_url}/api/job",
            params={
                "page[limit]": limit,
                "page[offset]": offset,
                "sort": "-postedAt",
                "filter[status]": "active"
            }
        )

        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Invalid jobs API response")

        records = payload.get("data")

        if not isinstance(records, list):
            raise ValueError("Invalid jobs API response")

        return records

    def fetch_company_name(
        self,
        company_id: str
    ) -> str | None:

        if company_id in self.company_cache:
            return self.company_cache[company_id]

        try:

            response = self.client.get(
                f"{self.base_url}/api/company/{company_id}"
            )

        except requests.HTTPError as error:

            if (
                error.response is not None
                and error.response.status_code == 404
            ):

                self.company_cache[company_id] = None

                self.logger.warning(
                    f"Company not found: {company_id}"
                )

                return None

            raise

        payload = response.json()

        company = payload.get("data") or {}
        attributes = company.get("attributes") or {}

        returned_id = company.get("id")

        if (
            returned_id is not None
            and str(returned_id) != company_id
        ):
            raise RuntimeError("Company API ID mismatch")

        name = attributes.get("name")

        if isinstance(name, str):
            name = " ".join(name.split()) or None
        else:
            name = None

        self.company_cache[company_id] = name

        return name

    def extract_company_id(self, job):

        attributes = job.get("attributes") or {}

        if attributes.get("hideCompany") is not False:
            return None

        relationships = job.get("relationships") or {}
        company = relationships.get("company") or {}
        company_data = company.get("data") or {}

        company_id = company_data.get("id")

        if not company_id:
            return None

        company_id = str(company_id)

        if not company_id.isascii() or not company_id.isdigit():
            raise ValueError("Invalid company ID")

        return company_id

    def extract_company_name(self, job):

        company_id = self.extract_company_id(job)

        if company_id is None:
            return None

        return self.fetch_company_name(company_id)

    def scrape(self) -> list[Opportunity]:

        opportunities = []

        seen_api_ids = set()
        seen_source_ids = set()

        self.company_cache.clear()

        self.stats = {
            "pages": 0,
            "fetched": 0,
            "duplicates": 0,
            "non_egyptian": 0,
            "inactive": 0,
            "expired": 0,
            "invalid": 0,
            "accepted": 0
        }

        offset = 0

        for page_number in range(self.max_pages):

            remaining = self.max_jobs - len(opportunities)

            if remaining <= 0:
                break

            limit = min(self.page_size, remaining)

            records = self.fetch_page(offset, limit)

            observed_at = datetime.now(timezone.utc)

            self.stats["pages"] += 1
            self.stats["fetched"] += len(records)

            if not records:
                break

            self.logger.info(
                f"Page {page_number + 1} | "
                f"Offset: {offset} | "
                f"Records: {len(records)}"
            )

            duplicate_records = 0

            for job in records:

                if len(opportunities) >= self.max_jobs:
                    break

                api_id = None

                try:

                    if not isinstance(job, dict):
                        raise ValueError("Invalid job record")

                    api_id = job.get("id")

                    if not isinstance(api_id, str) or not api_id.strip():
                        api_id = None
                        raise ValueError("Missing API ID")

                    if api_id in seen_api_ids:

                        self.stats["duplicates"] += 1
                        duplicate_records += 1

                        continue

                    seen_api_ids.add(api_id)

                    attributes = job.get("attributes")

                    if not isinstance(attributes, dict):
                        raise ValueError("Invalid attributes")

                    location = attributes.get("location") or {}
                    country = location.get("country") or {}

                    if attributes.get("status") != "active":

                        self.stats["inactive"] += 1
                        continue

                    if country.get("code") != "EG":

                        self.stats["non_egyptian"] += 1
                        continue

                    opportunity = self.mapper.map_job(
                        job,
                        observed_at=observed_at
                    )

                    source_id = opportunity.source_opportunity_id

                    if source_id in seen_source_ids:

                        self.stats["duplicates"] += 1
                        continue

                    if opportunity.status == "expired":

                        self.stats["expired"] += 1
                        continue

                    company_id = self.extract_company_id(job)

                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    AttributeError
                ) as error:

                    self.stats["invalid"] += 1

                    self.record_invalid(
                        raw_payload={"api_id": api_id},
                        error_type=type(error).__name__,
                        error_message="Invalid Wuzzuf opportunity"
                    )

                    continue

                # Network errors must not be treated
                # as invalid opportunity records.

                company_name = (
                    self.fetch_company_name(company_id)
                    if company_id is not None
                    else None
                )

                opportunity = Opportunity.model_validate({
                    **opportunity.model_dump(),
                    "organization": company_name
                })

                seen_source_ids.add(source_id)

                opportunities.append(opportunity)

                self.stats["accepted"] += 1

            if duplicate_records == len(records):

                self.logger.warning(
                    "Pagination returned only duplicate records"
                )

                break

            offset += len(records)

            if len(records) < limit:
                break

        self.logger.info(
            f"Collection statistics: {self.stats}"
        )

        self.logger.info(
            f"Unique companies cached: "
            f"{len(self.company_cache)}"
        )

        return opportunities