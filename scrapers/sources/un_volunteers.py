from datetime import datetime, timezone
from itertools import count

import requests
from requests.adapters import HTTPAdapter

from scrapers.base_scraper import BaseScraper
from scrapers.collection_result import StopReason

from scrapers.sources.un_volunteers_mapper import (
    map_un_volunteers_opportunity,
    validate_id,
    is_target_assignment,
    UNVExcludedOpportunity
)


class UNVResponseError(requests.HTTPError, RuntimeError):
    pass


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

            if value is None and name in {
                "max_jobs", "max_pages"
            }:
                continue

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
            "repeated_pages": 0,
            "overlapping_pages": 0,
            "pagination_anomalies": 0,
            "processed": 0,
            "unprocessed": 0,
            "last_reported_total": None,
            "total_changes": 0,
            "stop_reason": None,
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
            raise UNVResponseError(
                f"Unexpected HTTP status: "
                f"{response.status_code}",
                response=response,
            )

        content_type = response.headers.get(
            "Content-Type", ""
        )

        if "application/json" not in content_type.lower():
            raise ValueError(
                "Expected JSON response"
            )

        try:

            data = response.json()

        except requests.exceptions.JSONDecodeError as error:

            raise ValueError(
                "Invalid UNV JSON response"
            ) from error

        if not isinstance(data, dict):
            raise ValueError(
                "Invalid API response structure"
            )

        if data.get("isSuccess") is not True:
            raise UNVResponseError(
                "UNV API reported failure",
                response=response,
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

        if (
            type(value.get("skip")) is not int
            or value["skip"] != skip
        ):
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
            error_message="Invalid UNV assignment record",
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

            if type(listing.get("isOnsite")) is not bool:

                raise ValueError(
                    "Invalid assignment modality"
                )

            if not is_target_assignment(listing):

                seen.add(record_id)

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

                seen.add(record_id)

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

            seen.add(record_id)

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

        seen.add(record_id)

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
        page_signatures = set()
        discovered_ids = set()

        strict_pagination = (
            self.max_jobs is None
            or self.max_pages is None
        )

        skip = 0

        def finish(reason):

            self.stats["stop_reason"] = reason.value

            if self._running:

                if reason in {
                    StopReason.SOURCE_EXHAUSTED,
                    StopReason.REQUESTED_LIMIT,
                }:

                    self.mark_collection_complete(reason)

                else:

                    self.mark_collection_issue(reason)

            self.logger.info(
                "UNV collection stats: %s",
                self.stats,
            )

            return opportunities

        pages = (
            count(1)
            if self.max_pages is None
            else range(1, self.max_pages + 1)
        )

        for page in pages:

            try:

                records, total = self.fetch_listing(skip)

            except (
                requests.RequestException,
                PermissionError,
            ):

                finish(StopReason.SOURCE_ERROR)

                if not self._running:
                    raise

                return opportunities

            except ValueError:

                finish(StopReason.PARSING_ERROR)

                if not self._running:
                    raise

                return opportunities

            previous_total = self.stats[
                "last_reported_total"
            ]

            if (
                previous_total is not None
                and previous_total != total
            ):

                self.stats["total_changes"] += 1

            self.stats["last_reported_total"] = total

            self.stats["unprocessed"] = len(records)

            if strict_pagination:

                if (
                    previous_total is not None
                    and previous_total != total
                ):
                    self.stats["pagination_anomalies"] += 1
                    return finish(StopReason.PARSING_ERROR)

                expected_count = min(
                    self.page_size,
                    max(0, total - skip),
                )

                if len(records) != expected_count:
                    self.stats["pagination_anomalies"] += 1
                    return finish(StopReason.PARSING_ERROR)

            # Reject contradictory pagination evidence.

            if not records:

                return finish(
                    StopReason.PARSING_ERROR
                    if skip < total
                    else StopReason.SOURCE_EXHAUSTED
                )

            if (
                len(records) > self.page_size
                or skip >= total
                or skip + len(records) > total
            ):

                return finish(StopReason.PARSING_ERROR)

            # Detect repeated pages independently of
            # successful mapping and eligibility.

            signature = frozenset(
                listing["id"]
                for listing in records
                if isinstance(listing, dict)
                and type(listing.get("id")) is int
                and listing["id"] > 0
            )

            if signature and signature in page_signatures:

                self.stats["repeated_pages"] += 1

                return finish(StopReason.SOURCE_ERROR)

            if signature:

                page_signatures.add(signature)

            if strict_pagination:

                if len(signature) != len(records):
                    self.stats["pagination_anomalies"] += 1
                    return finish(StopReason.PARSING_ERROR)

                if discovered_ids.intersection(signature):
                    self.stats["overlapping_pages"] += 1
                    return finish(StopReason.PARSING_ERROR)

                discovered_ids.update(signature)

            for listing in records:

                try:

                    opportunity = self.collect_record(
                        listing,
                        seen,
                    )

                except (
                    requests.RequestException,
                    PermissionError,
                ):

                    finish(StopReason.SOURCE_ERROR)

                    if not self._running:
                        raise

                    return opportunities

                except ValueError:

                    finish(StopReason.PARSING_ERROR)

                    if not self._running:
                        raise

                    return opportunities

                self.stats["processed"] += 1
                self.stats["unprocessed"] -= 1

                if opportunity is not None:

                    opportunities.append(opportunity)

                if (
                    self.max_jobs is not None
                    and len(opportunities) >= self.max_jobs
                ):

                    return finish(
                        StopReason.REQUESTED_LIMIT
                    )

            skip += len(records)

            if skip >= total:

                return finish(
                    StopReason.SOURCE_EXHAUSTED
                )

            if (
                self.max_pages is not None
                and page >= self.max_pages
            ):

                return finish(
                    StopReason.REQUESTED_LIMIT
                )

        return finish(StopReason.REQUESTED_LIMIT)
