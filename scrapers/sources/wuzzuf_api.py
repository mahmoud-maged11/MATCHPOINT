from datetime import datetime, timezone
from itertools import count

import requests

from scrapers.base_scraper import BaseScraper
from scrapers.collection_result import StopReason
from scrapers.models import Opportunity
from scrapers.sources.wuzzuf_mapper import WuzzufMapper


class CompanyIdentityMismatchError(RuntimeError):
    pass


class WuzzufAPIScraper(BaseScraper):

    def __init__(
        self,
        max_jobs: int | None = 20,
        page_size: int = 20,
        max_pages: int | None = 10,
        persistent_company_cache=None
    ):

        super().__init__("wuzzuf")

        if max_jobs is not None and (
            type(max_jobs) is not int or max_jobs <= 0
        ):
            raise ValueError("max_jobs must be positive")

        if type(page_size) is not int or not 1 <= page_size <= 20:
            raise ValueError("page_size must be 1-20")

        if max_pages is not None and (
            type(max_pages) is not int or max_pages <= 0
        ):
            raise ValueError("max_pages must be positive")

        self.max_jobs = max_jobs
        self.page_size = page_size
        self.max_pages = max_pages

        self.base_url = self.source_config.base_url

        self.mapper = WuzzufMapper()

        self.company_cache: dict[str, str | None] = {}

        self.persistent_company_cache = persistent_company_cache
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

        try:

            payload = response.json()

        except requests.exceptions.JSONDecodeError as error:

            raise ValueError(
                "Invalid API JSON response"
            ) from error

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

        if self.persistent_company_cache is not None:

            found, cached_name = (
                self.persistent_company_cache.get(company_id)
            )

            if found:

                self.company_cache[company_id] = cached_name

                return cached_name

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

                if self.persistent_company_cache is not None:

                    self.persistent_company_cache.put(
                        company_id, None
                    )

                self.logger.warning(
                    f"Company not found: {company_id}"
                )

                return None

            raise

        try:

            payload = response.json()

        except requests.exceptions.JSONDecodeError as error:

            raise ValueError(
                "Invalid API JSON response"
            ) from error

        if not isinstance(payload, dict):

            raise ValueError(
                "Invalid company API response"
            )

        company = payload.get("data")

        if not isinstance(company, dict):

            raise ValueError(
                "Invalid company data"
            )

        attributes = company.get("attributes")

        if not isinstance(attributes, dict):

            raise ValueError(
                "Invalid company attributes"
            )

        returned_id = company.get("id")

        if returned_id is None:

            raise ValueError(
                "Missing company API ID"
            )

        if str(returned_id) != company_id:

            raise CompanyIdentityMismatchError(
                "Company API ID mismatch"
            )

        name = attributes.get("name")

        if isinstance(name, str):
            name = " ".join(name.split()) or None
        else:
            name = None

        self.company_cache[company_id] = name

        if (
            name is not None
            and self.persistent_company_cache is not None
        ):

            self.persistent_company_cache.put(
                company_id, name
            )

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

        deferred_companies = {}

        self.stats = {
            "pages": 0,
            "fetched": 0,
            "duplicates": 0,
            "pagination_anomalies": 0,
            "identity_conflicts": 0,
            "non_egyptian": 0,
            "inactive": 0,
            "expired": 0,
            "invalid": 0,
            "accepted": 0,
            "company_enrichment_deferred": 0,
            "company_request_failures": 0,
            "confidential_companies": 0
        }

        offset = 0

        page_numbers = (
            count()
            if self.max_pages is None
            else range(self.max_pages)
        )

        for page_number in page_numbers:

            remaining = (
                None
                if self.max_jobs is None
                else self.max_jobs - len(opportunities)
            )

            if remaining is not None and remaining <= 0:
                break

            limit = (
                self.page_size
                if remaining is None
                else min(self.page_size, remaining)
            )

            try:

                records = self.fetch_page(offset, limit)

            except requests.RequestException:

                if not self._running:
                    raise

                self.mark_collection_issue(
                    StopReason.SOURCE_ERROR
                )

                break

            except ValueError:

                if not self._running:
                    raise

                self.mark_collection_issue(
                    StopReason.PARSING_ERROR
                )

                break

            observed_at = datetime.now(timezone.utc)

            self.stats["pages"] += 1
            self.stats["fetched"] += len(records)

            if len(records) > limit:

                self.stats["pagination_anomalies"] += 1

                if not self._running:
                    raise ValueError("API page exceeds requested limit")

                self.mark_collection_issue(
                    StopReason.PARSING_ERROR
                )

                break

            if not records:

                if self._running:

                    self.mark_collection_complete(
                        StopReason.SOURCE_EXHAUSTED
                    )

                break

            self.logger.info(
                f"Page {page_number + 1} | "
                f"Offset: {offset} | "
                f"Records: {len(records)}"
            )

            duplicate_records = 0

            for job in records:

                if self.max_jobs is not None and len(opportunities) >= self.max_jobs:
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

                        if self._running:

                            self.mark_collection_issue(
                                StopReason.SOURCE_ERROR
                            )

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
                        self.stats["identity_conflicts"] += 1

                        if self._running:

                            self.mark_collection_issue(
                                StopReason.PARSING_ERROR
                            )

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

                company_name = None
                deferred_reason = None

                if attributes.get("hideCompany") is True:
                    self.stats["confidential_companies"] += 1

                if company_id is not None:

                    if company_id in deferred_companies:

                        deferred_reason = deferred_companies[
                            company_id
                        ]

                    else:

                        try:

                            company_name = self.fetch_company_name(
                                company_id
                            )

                        except requests.RequestException as error:

                            if not self._running:
                                raise

                            status_code = (
                                error.response.status_code
                                if error.response is not None
                                else None
                            )

                            if status_code in {401, 403}:

                                deferred_reason = "access_denied"

                            elif (
                                isinstance(
                                    error,
                                    (
                                        requests.ConnectionError,
                                        requests.Timeout,
                                    ),
                                )
                                or status_code in {
                                    500, 502, 503, 504
                                }
                            ):

                                deferred_reason = "temporary_failure"

                            else:

                                self.mark_collection_issue(
                                    StopReason.SOURCE_ERROR
                                )

                                return opportunities

                            deferred_companies[
                                company_id
                            ] = deferred_reason

                            self.stats[
                                "company_request_failures"
                            ] += 1

                            self.mark_collection_issue(
                                StopReason.SOURCE_ERROR
                            )

                            self.logger.warning(
                                "Company enrichment deferred | "
                                "Company ID: %s | Reason: %s",
                                company_id,
                                deferred_reason,
                            )

                        except (
                            ValueError,
                            CompanyIdentityMismatchError,
                        ):

                            if not self._running:
                                raise

                            self.mark_collection_issue(
                                StopReason.PARSING_ERROR
                            )

                            return opportunities

                raw_payload = dict(
                    opportunity.raw_payload
                )

                if company_id is not None:

                    raw_payload[
                        "company_id"
                    ] = company_id

                if deferred_reason is not None:

                    self.stats[
                        "company_enrichment_deferred"
                    ] += 1

                    raw_payload[
                        "_matchpoint_company_enrichment"
                    ] = deferred_reason

                opportunity = Opportunity.model_validate({
                    **opportunity.model_dump(),
                    "organization": company_name,
                    "raw_payload": raw_payload,
                })

                seen_source_ids.add(source_id)

                opportunities.append(opportunity)

                self.stats["accepted"] += 1

            if self.max_jobs is not None and len(opportunities) >= self.max_jobs:

                if self._running:

                    self.mark_collection_complete(
                        StopReason.REQUESTED_LIMIT
                    )

                break

            if duplicate_records:

                self.stats["pagination_anomalies"] += 1

                self.logger.warning(
                    "Pagination returned overlapping records"
                )

                if self._running:

                    self.mark_collection_issue(
                        StopReason.SOURCE_ERROR
                    )

                break

            offset += len(records)

            if len(records) < limit:

                if self._running:

                    self.mark_collection_complete(
                        StopReason.SOURCE_EXHAUSTED
                    )

                break

        else:

            if self._running:

                self.mark_collection_complete(
                    StopReason.REQUESTED_LIMIT
                )

        self.logger.info(
            f"Collection statistics: {self.stats}"
        )

        self.logger.info(
            f"Unique companies cached: "
            f"{len(self.company_cache)}"
        )

        return opportunities