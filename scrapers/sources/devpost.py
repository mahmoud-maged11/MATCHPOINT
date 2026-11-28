from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from scrapers.base_scraper import BaseScraper
from scrapers.collection_result import StopReason
from scrapers.models import Opportunity

from scrapers.sources.devpost_mapper import (
    DevpostExcludedOpportunity,
    DevpostEligibilityUnverified,
    map_devpost_opportunity,
    validate_source_id,
    validate_source_url,
)


class DevpostResponseError(requests.HTTPError, RuntimeError):
    pass


class DevpostScraper(BaseScraper):

    def __init__(
        self,
        max_jobs: int | None = 20,
        max_pages: int | None = 10
    ):

        super().__init__("devpost")

        if max_jobs is not None and (type(max_jobs) is not int or max_jobs <= 0):
            raise ValueError(
                "max_jobs must be a positive integer"
            )

        if max_pages is not None and (type(max_pages) is not int or max_pages <= 0):
            raise ValueError(
                "max_pages must be a positive integer"
            )

        self.max_jobs = max_jobs
        self.max_pages = max_pages

        self.api_url = (
            self.source_config.base_url.rstrip("/")
            + "/api/hackathons"
        )

        self.robots_cache = {}

        self.stats = {}

    def reset_stats(self):

        self.stats = {
            "listing_pages": 0,
            "repeated_pages": 0,
            "pagination_anomalies": 0,
            "identity_conflicts": 0,
            "status_results": {},
            "discovered": 0,
            "duplicates": 0,
            "excluded": 0,
            "eligibility_unverified": 0,
            "invalid": 0,
            "details_fetched": 0,
            "details_missing": 0,
            "accepted": 0,
            "open_accepted": 0,
            "upcoming_accepted": 0,
        }

    @staticmethod
    def validate_host(url):

        parsed = urlsplit(url)

        host = parsed.hostname

        if (
            parsed.scheme != "https"
            or not host
            or parsed.netloc != host
            or not (
                host == "devpost.com"
                or host.endswith(".devpost.com")
            )
        ):
            raise ValueError(
                "Unexpected Devpost host"
            )

        return host

    def request(self, url, params=None):

        self.validate_host(url)

        if not self.source_config.enabled:
            raise PermissionError(
                "Devpost collection is disabled"
            )

        self.client.rate_limiter.wait()

        self.logger.info(
            f"Requesting: {url}"
        )

        response = self.client.session.get(
            url,
            params=params,
            timeout=self.client.request_timeout,
            allow_redirects=False
        )

        response.raise_for_status()

        if response.status_code != 200:
            raise DevpostResponseError(
                f"Unexpected HTTP status: "
                f"{response.status_code}",
                response=response,
            )

        return response

    def get_robots(self, host):

        if host in self.robots_cache:
            return self.robots_cache[host]

        response = self.request(
            f"https://{host}/robots.txt"
        )

        robots = RobotFileParser()

        robots.parse(
            response.text.splitlines()
        )

        self.robots_cache[host] = robots

        return robots

    def fetch(self, url, params=None):

        host = self.validate_host(url)

        prepared_url = requests.Request(
            "GET",
            url,
            params=params
        ).prepare().url

        robots = self.get_robots(host)

        if not robots.can_fetch(
            "MATCHPOINT/1.0",
            prepared_url
        ):
            raise PermissionError(
                f"Disallowed by robots.txt: {url}"
            )

        return self.request(
            url,
            params=params
        )

    def fetch_listing(
        self,
        source_status,
        page
    ):

        response = self.fetch(
            self.api_url,
            params={
                "status[]": source_status,
                "location[]": "online",
                "page": page,
            }
        )

        try:

            payload = response.json()

        except requests.exceptions.JSONDecodeError as error:

            raise ValueError(
                "Invalid Devpost JSON response"
            ) from error

        if not isinstance(payload, dict):
            raise ValueError(
                "Unexpected Devpost API payload"
            )

        records = payload.get("hackathons")
        meta = payload.get("meta")

        if not isinstance(records, list):
            raise ValueError(
                "Missing Devpost hackathons list"
            )

        if not isinstance(meta, dict):
            raise ValueError(
                "Missing Devpost pagination metadata"
            )

        total_count = meta.get("total_count")
        per_page = meta.get("per_page")

        if (
            type(total_count) is not int
            or total_count < 0
            or type(per_page) is not int
            or per_page <= 0
        ):
            raise ValueError(
                "Invalid Devpost pagination metadata"
            )

        self.stats["listing_pages"] += 1

        self.logger.info(
            f"Listing | Status: {source_status} | "
            f"Page: {page} | "
            f"Records: {len(records)} | "
            f"Total: {total_count}"
        )

        return records, total_count, per_page

    def reject_record(
        self,
        record,
        error
    ):

        payload = {}

        if isinstance(record, dict):

            source_id = record.get("id")

            if type(source_id) is int:

                payload["id"] = source_id

            try:

                payload["url"] = validate_source_url(
                    record.get("url")
                )

            except ValueError:
                pass

            state = record.get("open_state")

            if state in ("open", "upcoming", "closed"):

                payload["open_state"] = state

        else:

            payload["record_type"] = type(record).__name__

        self.stats["invalid"] += 1

        self.record_invalid(
            raw_payload=payload,
            error_type=type(error).__name__,
            error_message="Invalid Devpost opportunity record",
            source_url=payload.get("url"),
        )

    def collect_record(
        self,
        record,
        seen_ids,
        seen_urls,
        expected_status
    ):

        self.stats["discovered"] += 1

        try:

            if not isinstance(record, dict):
                raise ValueError(
                    "Invalid listing record"
                )

            source_id = validate_source_id(
                record.get("id")
            )

            source_url = validate_source_url(
                record.get("url")
            )

            if (
                source_id in seen_ids
                or source_url in seen_urls
            ):
                self.stats["duplicates"] += 1
                return None

            if record.get("open_state") != expected_status:

                self.stats["excluded"] += 1
                return None

            if record.get("invite_only") is not False:

                self.stats["excluded"] += 1
                return None

            location = record.get(
                "displayed_location"
            )

            if not isinstance(location, dict):
                raise ValueError(
                    "Invalid displayed location"
                )

            location_name = location.get(
                "location"
            )

            if (
                not isinstance(location_name, str)
                or location_name.strip().casefold()
                != "online"
            ):

                self.stats["excluded"] += 1
                return None

        except ValueError as error:

            self.reject_record(
                record,
                error
            )

            return None

        try:

            response = self.fetch(source_url)

        except requests.HTTPError as error:

            if (
                error.response is not None
                and error.response.status_code
                in (404, 410)
            ):

                self.stats["details_missing"] += 1

                self.logger.warning(
                    f"Missing detail: {source_url}"
                )

                return None

            raise

        self.stats["details_fetched"] += 1

        try:

            opportunity = map_devpost_opportunity(
                record=record,
                detail_html=response.text,
                observed_at=datetime.now(
                    timezone.utc
                )
            )

        except DevpostEligibilityUnverified as error:

            self.stats["excluded"] += 1
            self.stats["eligibility_unverified"] += 1

            self.logger.warning(
                "Eligibility unverified for %s: %s",
                source_id,
                error,
            )

            return None

        except DevpostExcludedOpportunity as error:

            seen_ids.add(source_id)
            seen_urls.add(source_url)

            self.stats["excluded"] += 1

            self.logger.info(
                f"Excluded {source_id}: {error}"
            )

            return None

        except ValueError as error:

            self.reject_record(
                record,
                error
            )

            return None

        seen_ids.add(source_id)
        seen_urls.add(source_url)

        self.stats["accepted"] += 1

        if expected_status == "open":
            self.stats["open_accepted"] += 1

        else:
            self.stats["upcoming_accepted"] += 1

        return opportunity

    def scrape(self) -> list[Opportunity]:

        self.reset_stats()
        self.robots_cache.clear()

        opportunities = []

        seen_ids = set()
        seen_urls = set()

        identity_urls = {}
        url_identities = {}

        states = {
            status: {
                "page": 1,
                "finished": False,
                "buffer": [],
                "signatures": set(),
                "expected_total": None,
                "expected_per_page": None,
                "stop_reason": None,
                "pages": 0,
                "processed": 0,
                "accepted": 0,
            }
            for status in ("open", "upcoming")
        }

        def issue(state, reason):

            state["finished"] = True
            state["stop_reason"] = reason.value

            if self._running:

                self.mark_collection_issue(reason)

        def finish(reason):

            reports = {}

            for status, state in states.items():

                stop_reason = state["stop_reason"]

                if state["buffer"]:

                    if stop_reason not in (
                        StopReason.SOURCE_ERROR.value,
                        StopReason.PARSING_ERROR.value,
                    ):

                        stop_reason = reason.value

                if stop_reason is None:

                    stop_reason = reason.value

                reports[status] = {
                    "pages": state["pages"],
                    "processed": state["processed"],
                    "accepted": state["accepted"],
                    "unprocessed": len(state["buffer"]),
                    "stop_reason": stop_reason,
                    "completed": (
                        state["finished"]
                        and not state["buffer"]
                        and stop_reason in (
                            StopReason.SOURCE_EXHAUSTED.value,
                            StopReason.REQUESTED_LIMIT.value,
                        )
                    ),
                }

            self.stats["status_results"] = reports

            if (
                self._running
                and reason in (
                    StopReason.SOURCE_EXHAUSTED,
                    StopReason.REQUESTED_LIMIT,
                )
            ):

                self.mark_collection_complete(reason)

            self.logger.info(
                "Devpost collection stats: %s",
                self.stats,
            )

            return opportunities

        while (self.max_jobs is None or len(opportunities) < self.max_jobs):

            progress = False

            for source_status, state in states.items():

                if self.max_jobs is not None and len(opportunities) >= self.max_jobs:

                    return finish(
                        StopReason.REQUESTED_LIMIT
                    )

                if not state["buffer"]:

                    if state["finished"]:
                        continue

                    page = state["page"]

                    if self.max_pages is not None and page > self.max_pages:

                        state["finished"] = True

                        state["stop_reason"] = (
                            StopReason.REQUESTED_LIMIT.value
                        )

                        continue

                    try:

                        records, total_count, per_page = (
                            self.fetch_listing(
                                source_status,
                                page,
                            )
                        )

                    except (
                        requests.RequestException,
                        PermissionError,
                    ):

                        issue(
                            state,
                            StopReason.SOURCE_ERROR,
                        )

                        if not self._running:
                            raise

                        return finish(
                            StopReason.SOURCE_ERROR
                        )

                    except ValueError:

                        issue(
                            state,
                            StopReason.PARSING_ERROR,
                        )

                        if not self._running:
                            raise

                        continue

                    state["pages"] += 1
                    state["page"] += 1

                    progress = True

                    offset = (page - 1) * per_page

                    if state["expected_total"] is None:

                        state["expected_total"] = total_count
                        state["expected_per_page"] = per_page

                    expected_count = min(
                        per_page,
                        max(0, total_count - offset),
                    )

                    if (
                        total_count != state["expected_total"]
                        or per_page != state["expected_per_page"]
                        or len(records) != expected_count
                    ):

                        self.stats["pagination_anomalies"] += 1

                        self.logger.warning(
                            "Pagination anomaly: status=%s "
                            "page=%s expected=%s received=%s",
                            source_status,
                            page,
                            expected_count,
                            len(records),
                        )

                        issue(
                            state,
                            StopReason.PARSING_ERROR,
                        )

                        continue

                    if not records:

                        state["finished"] = True

                        state["stop_reason"] = (
                            StopReason.SOURCE_EXHAUSTED.value
                        )

                        continue

                    # Detect repeated pages within each
                    # status, not across different statuses.

                    signature = frozenset(
                        record["id"]
                        for record in records
                        if isinstance(record, dict)
                        and type(record.get("id")) is int
                        and record["id"] > 0
                    )

                    if (
                        self._running
                        and signature
                        and signature in state["signatures"]
                    ):

                        self.stats["repeated_pages"] += 1

                        issue(
                            state,
                            StopReason.SOURCE_ERROR,
                        )

                        return finish(
                            StopReason.SOURCE_ERROR
                        )

                    if signature:

                        state["signatures"].add(signature)

                    state["buffer"].extend(records)

                    if page * per_page >= total_count:

                        state["finished"] = True

                        state["stop_reason"] = (
                            StopReason.SOURCE_EXHAUSTED.value
                        )

                    elif self.max_pages is not None and page >= self.max_pages:

                        state["finished"] = True

                        state["stop_reason"] = (
                            StopReason.REQUESTED_LIMIT.value
                        )

                if not state["buffer"]:
                    continue

                record = state["buffer"].pop(0)

                progress = True
                state["processed"] += 1

                # Detect contradictory identity evidence
                # instead of silently merging records.

                if isinstance(record, dict):

                    try:

                        source_id = validate_source_id(
                            record.get("id")
                        )

                        source_url = validate_source_url(
                            record.get("url")
                        )

                    except ValueError:

                        source_id = None
                        source_url = None

                    if source_id and source_url:

                        if (
                            identity_urls.get(
                                source_id, source_url
                            ) != source_url
                            or url_identities.get(
                                source_url, source_id
                            ) != source_id
                        ):

                            self.stats[
                                "identity_conflicts"
                            ] += 1

                            self.stats["discovered"] += 1

                            self.reject_record(
                                record,
                                ValueError(
                                    "Conflicting identity"
                                ),
                            )

                            if self._running:

                                self.mark_collection_issue(
                                    StopReason.PARSING_ERROR
                                )

                            continue

                try:

                    opportunity = self.collect_record(
                        record=record,
                        seen_ids=seen_ids,
                        seen_urls=seen_urls,
                        expected_status=source_status,
                    )

                except (
                    requests.RequestException,
                    PermissionError,
                ):

                    issue(
                        state,
                        StopReason.SOURCE_ERROR,
                    )

                    if not self._running:
                        raise

                    return finish(
                        StopReason.SOURCE_ERROR
                    )

                except ValueError:

                    issue(
                        state,
                        StopReason.PARSING_ERROR,
                    )

                    if not self._running:
                        raise

                    return finish(
                        StopReason.PARSING_ERROR
                    )

                if opportunity is not None:

                    opportunities.append(opportunity)
                    state["accepted"] += 1

                    if isinstance(opportunity, Opportunity):

                        source_id = (
                            opportunity.source_opportunity_id
                        )

                        source_url = str(
                            opportunity.source_url
                        )

                        identity_urls[source_id] = source_url
                        url_identities[source_url] = source_id

            if not progress:
                break

        if self.max_jobs is not None and len(opportunities) >= self.max_jobs:

            return finish(
                StopReason.REQUESTED_LIMIT
            )

        reasons = {
            state["stop_reason"]
            for state in states.values()
        }

        if StopReason.SOURCE_ERROR.value in reasons:

            return finish(StopReason.SOURCE_ERROR)

        if StopReason.PARSING_ERROR.value in reasons:

            return finish(StopReason.PARSING_ERROR)

        if StopReason.REQUESTED_LIMIT.value in reasons:

            return finish(StopReason.REQUESTED_LIMIT)

        return finish(StopReason.SOURCE_EXHAUSTED)
