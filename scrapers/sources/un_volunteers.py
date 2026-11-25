from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter

from scrapers.base_scraper import BaseScraper

from scrapers.sources.un_volunteers_mapper import (
    map_un_volunteers_opportunity,
    validate_id,
    is_target_assignment,
    UNVExcludedOpportunity
)


class UNVolunteersScraper(BaseScraper):

    BASE_URL = "https://app.unv.org"

    SEARCH_URL = (
        BASE_URL
        + "/api/doa/doa/"
        + "SearchDoaAsyncByAzureCognitive"
    )

    DETAILS_URL = BASE_URL + "/api/doa/doa"

    def __init__(
        self,
        max_jobs=30,
        page_size=10,
        max_pages=30
    ):

        super().__init__("un_volunteers")
        self.client.session.mount(
            "https://",
            HTTPAdapter(max_retries=0)
        )

        for name, value in (
            ("max_jobs", max_jobs),
            ("page_size", page_size),
            ("max_pages", max_pages)
        ):

            if type(value) is not int or value <= 0:
                raise ValueError(
                    f"{name} must be a positive integer"
                )

        self.max_jobs = max_jobs
        self.page_size = page_size
        self.max_pages = max_pages

        self.reset_stats()

    def reset_stats(self):

        self.stats = {
            "listing_pages": 0,
            "discovered": 0,
            "duplicates": 0,
            "excluded": 0,
            "invalid": 0,
            "details_fetched": 0,
            "details_missing": 0,
            "accepted": 0,
            "online_accepted": 0,
            "onsite_accepted": 0,
            "active_accepted": 0,
            "unknown_accepted": 0
        }

    def request_json(
        self,
        method,
        url,
        payload=None
    ):

        if not self.client.source_config.enabled:
            raise PermissionError(
                "UN Volunteers source is disabled"
            )

        self.client.rate_limiter.wait()

        response = self.client.session.request(
            method,
            url,
            json=payload,
            timeout=self.client.request_timeout,
            allow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": "MATCHPOINT/1.0"
            }
        )

        response.raise_for_status()

        if response.status_code != 200:
            raise RuntimeError(
                f"Unexpected HTTP status: "
                f"{response.status_code}"
            )

        content_type = response.headers.get(
            "Content-Type", ""
        )

        if "application/json" not in content_type.lower():
            raise ValueError(
                "Expected JSON response"
            )

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "Invalid API response structure"
            )

        if data.get("isSuccess") is not True:
            raise RuntimeError(
                "UNV API reported failure"
            )

        value = data.get("value")

        if not isinstance(value, dict):
            raise ValueError(
                "Invalid API value structure"
            )

        self.logger.info(
            "UNV %s %s HTTP %s",
            method,
            url,
            response.status_code
        )

        return value

    def fetch_listing(self, skip):

        payload = {
            "filters": [],
            "take": self.page_size,
            "skip": skip
        }

        value = self.request_json(
            "POST",
            self.SEARCH_URL,
            payload
        )

        records = value.get("result")
        total = value.get("total")

        if not isinstance(records, list):
            raise ValueError(
                "Invalid assignment listing"
            )

        if type(total) is not int or total < 0:
            raise ValueError(
                "Invalid assignment total"
            )

        if value.get("skip") != skip:
            raise ValueError(
                "Pagination offset mismatch"
            )

        if len(records) > self.page_size:
            raise ValueError(
                "Unexpected listing page size"
            )

        self.stats["listing_pages"] += 1
        self.stats["discovered"] += len(records)

        self.logger.info(
            "UNV listing skip=%s records=%s total=%s",
            skip,
            len(records),
            total
        )

        return records, total

    def fetch_detail(self, record_id):

        return self.request_json(
            "GET",
            f"{self.DETAILS_URL}/{record_id}"
        )

    def reject_invalid(
        self,
        record_id,
        error
    ):

        self.stats["invalid"] += 1

        source_url = (
            f"{self.BASE_URL}/opportunities/{record_id}"
            if type(record_id) is int and record_id > 0
            else None
        )

        self.record_invalid(
            raw_payload={
                "assignment_id": (
                    record_id
                    if type(record_id) is int
                    else None
                )
            },
            error_type=type(error).__name__,
            error_message=str(error),
            source_url=source_url
        )

    def collect_record(self, listing, seen):

        record_id = None

        try:

            if not isinstance(listing, dict):
                raise ValueError(
                    "Invalid listing record"
                )

            record_id = validate_id(
                listing.get("id")
            )

            if record_id in seen:

                self.stats["duplicates"] += 1

                return None

            seen.add(record_id)

            if not is_target_assignment(listing):

                self.stats["excluded"] += 1

                return None

        except (ValueError, TypeError) as error:

            self.reject_invalid(
                record_id, error
            )

            return None

        try:

            detail = self.fetch_detail(record_id)

            self.stats["details_fetched"] += 1

        except requests.HTTPError as error:

            response = error.response

            if (
                response is not None
                and response.status_code in (404, 410)
            ):

                self.stats["details_missing"] += 1

                return None

            raise

        try:

            opportunity = (
                map_un_volunteers_opportunity(
                    listing,
                    detail,
                    datetime.now(timezone.utc)
                )
            )

        except UNVExcludedOpportunity as error:

            self.stats["excluded"] += 1

            self.logger.info(
                "UNV excluded %s: %s",
                record_id,
                error
            )

            return None

        except (ValueError, TypeError) as error:

            self.reject_invalid(
                record_id, error
            )

            return None

        self.stats["accepted"] += 1

        if detail.get("isOnsite") is False:
            self.stats["online_accepted"] += 1
        else:
            self.stats["onsite_accepted"] += 1

        if opportunity.status == "active":
            self.stats["active_accepted"] += 1
        else:
            self.stats["unknown_accepted"] += 1

        return opportunity

    def scrape(self):

        self.reset_stats()

        opportunities = []
        seen = set()

        skip = 0

        for _ in range(self.max_pages):

            records, total = self.fetch_listing(
                skip
            )

            if not records:
                break

            for listing in records:

                opportunity = self.collect_record(
                    listing,
                    seen
                )

                if opportunity is not None:
                    opportunities.append(
                        opportunity
                    )

                if len(opportunities) >= self.max_jobs:
                    break

            if len(opportunities) >= self.max_jobs:
                break

            skip += len(records)

            if skip >= total:
                break

        self.logger.info(
            "UNV collection stats: %s",
            self.stats
        )

        return opportunities