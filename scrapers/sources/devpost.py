from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from scrapers.base_scraper import BaseScraper
from scrapers.models import Opportunity

from scrapers.sources.devpost_mapper import (
    DevpostExcludedOpportunity,
    map_devpost_opportunity,
    validate_source_id,
    validate_source_url,
)


class DevpostScraper(BaseScraper):

    def __init__(
        self,
        max_jobs: int = 20,
        max_pages: int = 10
    ):

        super().__init__("devpost")

        if type(max_jobs) is not int or max_jobs <= 0:
            raise ValueError(
                "max_jobs must be a positive integer"
            )

        if type(max_pages) is not int or max_pages <= 0:
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
            "discovered": 0,
            "duplicates": 0,
            "excluded": 0,
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
            raise RuntimeError(
                f"Unexpected HTTP status: "
                f"{response.status_code}"
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

        payload = response.json()

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

        payload = (
            record
            if isinstance(record, dict)
            else {"record": record}
        )

        source_url = payload.get("url")

        if not isinstance(source_url, str):
            source_url = None

        self.stats["invalid"] += 1

        self.record_invalid(
            raw_payload=payload,
            error_type=type(error).__name__,
            error_message=str(error),
            source_url=source_url
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

            seen_ids.add(source_id)
            seen_urls.add(source_url)

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

        except DevpostExcludedOpportunity as error:

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

        states = {
            "open": {
                "page": 1,
                "finished": False,
                "buffer": [],
            },
            "upcoming": {
                "page": 1,
                "finished": False,
                "buffer": [],
            },
        }

        while len(opportunities) < self.max_jobs:

            progress = False

            for source_status, state in states.items():

                if len(opportunities) >= self.max_jobs:
                    break

                if not state["buffer"]:

                    if state["finished"]:
                        continue

                    page = state["page"]

                    if page > self.max_pages:

                        state["finished"] = True
                        continue

                    records, total_count, per_page = (
                        self.fetch_listing(
                            source_status,
                            page
                        )
                    )

                    state["page"] += 1

                    state["buffer"].extend(records)

                    if (
                        not records
                        or page * per_page >= total_count
                        or page >= self.max_pages
                    ):
                        state["finished"] = True

                    progress = True

                if not state["buffer"]:
                    continue

                record = state["buffer"].pop(0)

                progress = True

                opportunity = self.collect_record(
                    record=record,
                    seen_ids=seen_ids,
                    seen_urls=seen_urls,
                    expected_status=source_status
                )

                if opportunity is not None:

                    opportunities.append(
                        opportunity
                    )

            if not progress:
                break

        self.logger.info(
            f"Devpost collection stats: {self.stats}"
        )

        return opportunities