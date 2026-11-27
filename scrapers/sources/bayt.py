
import json
import re

from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.sources.bayt_mapper import BaytMapper


class BaytScraper(BaseScraper):

    BASE_URL = "https://www.bayt.com"

    LISTING_URL = BASE_URL + "/en/egypt/jobs/"

    USER_AGENT = "MATCHPOINT/1.0"

    def __init__(self, max_jobs=20, max_pages=10):

        if max_jobs <= 0 or max_pages <= 0:
            raise ValueError(
                "Collection limits must be positive"
            )

        super().__init__("bayt")

        self.max_jobs = max_jobs
        self.max_pages = max_pages

        self.robots = None
        self.stats = {}

    @classmethod
    def validate_url(cls, url):

        parsed = urlparse(url)

        if (
            parsed.scheme != "https"
            or parsed.netloc != "www.bayt.com"
            or parsed.fragment
        ):
            raise ValueError("Unexpected Bayt URL")

        if parsed.path == "/robots.txt" and not parsed.query:
            return

        if parsed.path == "/en/egypt/jobs/":

            if not parsed.query:
                return

            if re.fullmatch(
                r"page=[1-9]\d*",
                parsed.query
            ):
                return

            raise ValueError("Invalid listing query")

        BaytMapper.extract_job_id(url)

    def load_robots(self):

        url = self.BASE_URL + "/robots.txt"

        response = self.client.get(url)

        if response.url != url:
            raise PermissionError(
                "Unexpected robots redirect"
            )

        if response.status_code != 200:
            raise PermissionError(
                "Robots policy requires review"
            )

        self.robots = RobotFileParser()
        self.robots.set_url(url)
        self.robots.parse(response.text.splitlines())

        self.stats["robots_status"] = response.status_code

    def fetch_html(self, url):

        self.validate_url(url)

        if self.robots is None:
            raise PermissionError(
                "Robots policy not initialized"
            )

        if not self.robots.can_fetch(self.USER_AGENT, url):
            raise PermissionError(
                f"Disallowed URL: {url}"
            )

        response = self.client.get(url)

        if response.url != url:
            raise PermissionError(
                "Unexpected response redirect"
            )

        if response.status_code != 200:
            raise ValueError(
                "Unexpected HTML response status"
            )

        return response.content.decode(
            "utf-8-sig",
            errors="strict"
        )

    @staticmethod
    def parse_flag(value):

        if value == "1":
            return True

        if value == "0":
            return False

        return None

    @classmethod
    def extract_jobs(cls, html):

        soup = BeautifulSoup(html, "html.parser")

        jobs = {}

        def add_job(href, metadata=None):

            if not isinstance(href, str):
                return

            url = urljoin(cls.BASE_URL, href)

            try:
                job_id = BaytMapper.extract_job_id(url)

            except ValueError:
                return

            if job_id not in jobs:

                jobs[job_id] = {
                    "job_id": job_id,
                    "url": url,
                    "is_aggregated": None,
                    "is_external": None,
                }

            if metadata:
                jobs[job_id].update(metadata)

        for link in soup.select(
            'h2 a[data-js-aid="jobID"][href]'
        ):

            add_job(
                link["href"],
                {
                    "is_aggregated": cls.parse_flag(
                        link.get(
                            "data-automation-is_aggregated"
                        )
                    ),
                    "is_external": cls.parse_flag(
                        link.get(
                            "data-automation-is_external"
                        )
                    ),
                }
            )

        for script in soup.select(
            'script[type="application/ld+json"]'
        ):

            try:
                data = json.loads(script.get_text())

            except json.JSONDecodeError:
                continue

            if not isinstance(data, dict):
                continue

            if data.get("@type") != "ItemList":
                continue

            items = data.get("itemListElement", [])

            if not isinstance(items, list):
                continue

            for item in items:

                if isinstance(item, dict):
                    add_job(item.get("url"))

        return list(jobs.values())

    @classmethod
    def extract_next_page(cls, html, current_page):

        soup = BeautifulSoup(html, "html.parser")

        expected = current_page + 1

        for link in soup.select(
            "a.jsAjaxLoad[href], a[rel='next'][href]"
        ):

            url = urljoin(cls.BASE_URL, link["href"])

            parsed = urlparse(url)

            if (
                parsed.scheme == "https"
                and parsed.netloc == "www.bayt.com"
                and parsed.path == "/en/egypt/jobs/"
                and parsed.query == f"page={expected}"
                and not parsed.fragment
            ):
                return url

        return None

    def scrape(self):

        self.stats = {
            "robots_status": None,
            "listing_pages": 0,
            "jobs_discovered": 0,
            "details_fetched": 0,
            "duplicates": 0,
            "unavailable": 0,
            "non_egypt": 0,
            "invalid": 0,
            "accepted": 0,
            "active": 0,
            "expired": 0,
            "closed": 0,
            "unknown": 0,
            "aggregated": 0,
            "external": 0,
        }

        self.load_robots()

        opportunities = []
        seen = set()

        page = 1
        url = self.LISTING_URL

        while (
            url
            and page <= self.max_pages
            and len(opportunities) < self.max_jobs
        ):

            html = self.fetch_html(url)

            self.stats["listing_pages"] += 1

            jobs = self.extract_jobs(html)

            self.stats["jobs_discovered"] += len(jobs)

            if not jobs:
                raise ValueError(
                    f"No job links extracted from page {page}"
                )

            next_url = self.extract_next_page(
                html,
                page
            )

            for job in jobs:

                if len(opportunities) >= self.max_jobs:
                    break

                job_id = job["job_id"]
                job_url = job["url"]

                if job_id in seen:
                    self.stats["duplicates"] += 1
                    continue

                seen.add(job_id)

                try:

                    detail_html = self.fetch_html(job_url)

                    self.stats["details_fetched"] += 1

                    opportunity = BaytMapper.map_job(
                        job_url,
                        detail_html,
                        listing=job,
                    )

                    if opportunity is None:
                        self.stats["non_egypt"] += 1
                        continue

                except requests.HTTPError as error:

                    response = error.response

                    if (
                        response is not None
                        and response.status_code in (404, 410)
                    ):
                        self.stats["unavailable"] += 1
                        continue

                    raise

                except (ValueError, TypeError) as error:

                    self.stats["invalid"] += 1

                    self.record_invalid(
                        raw_payload=job,
                        error_type=type(error).__name__,
                        error_message=str(error),
                        source_url=job_url,
                    )

                    continue

                opportunities.append(opportunity)

                self.stats["accepted"] += 1

                self.stats[opportunity.status] += 1

                if job["is_aggregated"] is True:
                    self.stats["aggregated"] += 1

                if job["is_external"] is True:
                    self.stats["external"] += 1

            url = next_url
            page += 1

        self.logger.info(
            "Bayt collection stats: %s",
            self.stats
        )

        return opportunities
