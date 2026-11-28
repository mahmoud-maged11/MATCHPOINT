
import json
import re

from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.collection_result import StopReason
from scrapers.sources.bayt_mapper import BaytMapper


class UnsafeJobRedirect(PermissionError):
    pass


class BaytScraper(BaseScraper):

    BASE_URL = "https://www.bayt.com"

    LISTING_URL = BASE_URL + "/en/egypt/jobs/"

    USER_AGENT = "MATCHPOINT/1.0"

    def __init__(self, max_jobs=20, max_pages=10):

        for name, value in (
            ("max_jobs", max_jobs),
            ("max_pages", max_pages),
        ):
            if value is not None and (
                type(value) is not int or value <= 0
            ):
                raise ValueError(
                    f"{name} must be a positive integer or None"
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

        response = self.client.get(url, allow_redirects=False)

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

        try:
            original_job_id = BaytMapper.extract_job_id(url)

        except ValueError:
            original_job_id = None

        current_url = url
        visited = {url}
        redirect_count = 0

        while True:

            self.validate_url(current_url)

            if not self.robots.can_fetch(
                self.USER_AGENT,
                current_url,
            ):
                raise PermissionError(
                    f"Disallowed URL: {current_url}"
                )

            response = self.client.get(
                current_url,
                allow_redirects=False,
            )

            if response.url != current_url:
                raise PermissionError(
                    "Unexpected response redirect"
                )

            if response.status_code in {
                301, 302, 303, 307, 308
            }:

                if original_job_id is None:
                    raise PermissionError(
                        "Unexpected listing redirect"
                    )

                location = response.headers.get(
                    "Location"
                )

                if not isinstance(location, str) or not location.strip():
                    raise UnsafeJobRedirect(
                        "Missing redirect location"
                    )

                try:

                    target_url = urljoin(
                        current_url,
                        location,
                    )

                    self.validate_url(target_url)

                    target_job_id = (
                        BaytMapper.extract_job_id(
                            target_url
                        )
                    )

                except ValueError as error:

                    raise UnsafeJobRedirect(
                        "Unverified job redirect target"
                    ) from error

                if target_job_id != original_job_id:

                    raise UnsafeJobRedirect(
                        "Redirect job identity mismatch"
                    )

                if target_url in visited:
                    raise PermissionError(
                        "Bayt redirect loop"
                    )

                redirect_count += 1

                if redirect_count > 3:
                    raise PermissionError(
                        "Bayt redirect limit exceeded"
                    )

                visited.add(target_url)
                current_url = target_url

                continue

            if response.status_code != 200:
                raise requests.HTTPError(
                    "Unexpected HTML response status",
                    response=response,
                )

            return response.content.decode(
                "utf-8-sig",
                errors="strict",
            )

    @staticmethod
    def parse_flag(value):

        if value == "1":
            return True

        if value == "0":
            return False

        return None

    @classmethod
    def extract_jobs_with_diagnostics(
        cls, html, *, soup=None
    ):

        if soup is None:
            soup = BeautifulSoup(html, "html.parser")

        jobs = {}
        invalid = 0

        def add_job(href, metadata=None):

            nonlocal invalid

            if not isinstance(href, str) or not href.strip():

                invalid += 1
                return

            try:

                url = urljoin(cls.BASE_URL, href)
                job_id = BaytMapper.extract_job_id(url)

            except ValueError:

                invalid += 1
                return

            if job_id not in jobs:

                jobs[job_id] = {
                    "job_id": job_id,
                    "url": url,
                    "is_aggregated": None,
                    "is_external": None,
                }

            if metadata:

                for key, value in metadata.items():

                    if value is not None:
                        jobs[job_id][key] = value

        for link in soup.select(
            'h2 a[data-js-aid="jobID"]'
        ):

            add_job(
                link.get("href"),
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
                },
            )

        for script in soup.select(
            'script[type="application/ld+json"]'
        ):

            try:

                data = json.loads(script.get_text())

            except json.JSONDecodeError:

                # Unrelated malformed JSON-LD is not
                # sufficient evidence of listing failure.
                continue

            if not isinstance(data, dict):
                continue

            if data.get("@type") != "ItemList":
                continue

            items = data.get("itemListElement")

            if not isinstance(items, list):

                invalid += 1
                continue

            for item in items:

                if not isinstance(item, dict):

                    invalid += 1
                    continue

                add_job(item.get("url"))

        return list(jobs.values()), invalid

    @classmethod
    def extract_jobs(cls, html):

        jobs, _ = cls.extract_jobs_with_diagnostics(
            html
        )

        return jobs


    @classmethod
    def extract_next_page_with_diagnostics(
        cls, html, current_page, *, soup=None
    ):

        if soup is None:
            soup = BeautifulSoup(html, "html.parser")

        expected = current_page + 1
        invalid = 0
        candidates = set()
        future_pages = set()

        for link in soup.select(
            "a.jsAjaxLoad, a[rel='next']"
        ):

            relations = link.get("rel", [])

            if isinstance(relations, str):
                relations = relations.split()

            explicit_next = "next" in relations

            href = link.get("href")

            if not isinstance(href, str) or not href.strip():

                if explicit_next:
                    invalid += 1

                continue

            try:

                url = urljoin(cls.BASE_URL, href)
                parsed = urlparse(url)

            except ValueError:

                invalid += 1
                continue

            is_listing_path = (
                parsed.path == "/en/egypt/jobs/"
            )

            if not explicit_next and not is_listing_path:
                continue

            try:

                cls.validate_url(url)

            except ValueError:

                invalid += 1
                continue

            if not is_listing_path:

                invalid += 1
                continue

            if not parsed.query:

                target_page = 1

            else:

                match = re.fullmatch(
                    r"page=([1-9][0-9]*)",
                    parsed.query
                )

                if not match:

                    invalid += 1
                    continue

                target_page = int(match.group(1))

            if target_page > current_page:

                future_pages.add(target_page)

            if target_page == expected:

                candidates.add(url)

            elif explicit_next:

                invalid += 1

            # Other valid numbered pages are navigation,
            # not parsing errors.

        next_url = next(iter(candidates), None)

        if next_url is None and future_pages and invalid == 0:

            invalid += 1

        return next_url, invalid

    @classmethod
    def extract_next_page(cls, html, current_page):

        next_url, _ = (
            cls.extract_next_page_with_diagnostics(
                html, current_page
            )
        )

        return next_url

    def scrape(self):

        self.robots = None

        self.stats = {
            "robots_status": None,
            "listing_pages": 0,
            "jobs_discovered": 0,
            "details_fetched": 0,
            "duplicates": 0,
            "unavailable": 0,
            "unsafe_job_redirects": 0,
            "non_egypt": 0,
            "invalid": 0,
            "invalid_listing_links": 0,
            "invalid_pagination_links": 0,
            "repeated_pages": 0,
            "pagination_overlaps": 0,
            "overlapping_job_ids": 0,
            "accepted": 0,
            "active": 0,
            "expired": 0,
            "closed": 0,
            "unknown": 0,
            "aggregated": 0,
            "external": 0,
        }

        opportunities = []
        seen = set()
        discovered = set()
        page_signatures = set()
        consecutive_unsafe_redirects = 0

        def issue(reason):

            if self._running:

                self.mark_collection_issue(reason)

        def finish(reason):

            if (
                self._running
                and reason in {
                    StopReason.SOURCE_EXHAUSTED,
                    StopReason.REQUESTED_LIMIT,
                }
            ):

                self.mark_collection_complete(reason)

            self.logger.info(
                "Bayt collection stats: %s",
                self.stats,
            )

            return opportunities

        try:

            self.load_robots()

        except (
            requests.RequestException,
            PermissionError,
        ):

            issue(StopReason.SOURCE_ERROR)
            raise

        except ValueError:

            issue(StopReason.PARSING_ERROR)
            raise

        page = 1
        url = self.LISTING_URL

        while url and (
            self.max_pages is None
            or page <= self.max_pages
        ):

            try:

                html = self.fetch_html(url)

            except (
                requests.RequestException,
                PermissionError,
            ):

                issue(StopReason.SOURCE_ERROR)

                if not self._running or not opportunities:
                    raise

                return finish(StopReason.SOURCE_ERROR)

            except ValueError:

                issue(StopReason.PARSING_ERROR)

                if not self._running or not opportunities:
                    raise

                return finish(StopReason.PARSING_ERROR)

            self.stats["listing_pages"] += 1

            listing_soup = BeautifulSoup(
                html, "html.parser"
            )

            jobs, invalid = (
                self.extract_jobs_with_diagnostics(
                    html, soup=listing_soup
                )
            )

            self.stats["jobs_discovered"] += len(jobs)
            self.stats["invalid_listing_links"] += invalid

            if invalid:

                issue(StopReason.PARSING_ERROR)

            if not jobs:

                issue(StopReason.PARSING_ERROR)

                if not self._running or not opportunities:

                    raise ValueError(
                        f"No job links extracted from page {page}"
                    )

                return finish(StopReason.PARSING_ERROR)

            signature = frozenset(
                job["job_id"] for job in jobs
            )

            if (
                signature in page_signatures
                or signature.issubset(discovered)
            ):

                self.stats["repeated_pages"] += 1

                issue(StopReason.SOURCE_ERROR)

                return finish(StopReason.SOURCE_ERROR)

            overlap = set(signature).intersection(discovered)

            if overlap:

                self.stats["pagination_overlaps"] += 1
                self.stats["overlapping_job_ids"] += len(overlap)

                if (
                    self.max_jobs is None
                    and self.max_pages is None
                ):
                    issue(StopReason.SOURCE_ERROR)

            page_signatures.add(signature)
            discovered.update(signature)

            for job in jobs:

                if self.max_jobs is not None and len(opportunities) >= self.max_jobs:

                    return finish(
                        StopReason.REQUESTED_LIMIT
                    )

                job_id = job["job_id"]
                job_url = job["url"]

                if job_id in seen:

                    self.stats["duplicates"] += 1
                    continue

                # Request failures are not invalid records.

                try:

                    detail_html = self.fetch_html(job_url)

                    consecutive_unsafe_redirects = 0

                except UnsafeJobRedirect:

                    self.stats["unsafe_job_redirects"] += 1

                    consecutive_unsafe_redirects += 1

                    seen.add(job_id)

                    issue(StopReason.SOURCE_ERROR)

                    self.logger.warning(
                        "Unsafe Bayt redirect isolated | Job ID: %s",
                        job_id,
                    )

                    if consecutive_unsafe_redirects >= 3:

                        if not self._running or not opportunities:
                            raise

                        return finish(StopReason.SOURCE_ERROR)

                    continue

                except requests.HTTPError as error:

                    response = error.response

                    if (
                        response is not None
                        and response.status_code in (404, 410)
                    ):

                        self.stats["unavailable"] += 1
                        seen.add(job_id)
                        continue

                    issue(StopReason.SOURCE_ERROR)

                    if not self._running or not opportunities:
                        raise

                    return finish(StopReason.SOURCE_ERROR)

                except (
                    requests.RequestException,
                    PermissionError,
                ):

                    issue(StopReason.SOURCE_ERROR)

                    if not self._running or not opportunities:
                        raise

                    return finish(StopReason.SOURCE_ERROR)

                except ValueError:

                    issue(StopReason.PARSING_ERROR)

                    if not self._running or not opportunities:
                        raise

                    return finish(StopReason.PARSING_ERROR)

                self.stats["details_fetched"] += 1

                try:

                    opportunity = BaytMapper.map_job(
                        job_url,
                        detail_html,
                        listing=job,
                    )

                except (ValueError, TypeError) as error:

                    self.stats["invalid"] += 1

                    self.record_invalid(
                        raw_payload=job,
                        error_type=type(error).__name__,
                        error_message="Invalid Bayt job details",
                        source_url=job_url,
                    )

                    continue

                # Reserve identity after successful mapping
                # or a confirmed filtering decision.

                seen.add(job_id)

                if opportunity is None:

                    self.stats["non_egypt"] += 1
                    continue

                opportunities.append(opportunity)

                self.stats["accepted"] += 1
                self.stats[opportunity.status] += 1

                if job["is_aggregated"] is True:

                    self.stats["aggregated"] += 1

                if job["is_external"] is True:

                    self.stats["external"] += 1

            if self.max_jobs is not None and len(opportunities) >= self.max_jobs:

                return finish(StopReason.REQUESTED_LIMIT)

            next_url, invalid = (
                self.extract_next_page_with_diagnostics(
                    html, page, soup=listing_soup
                )
            )

            self.stats["invalid_pagination_links"] += invalid

            if invalid:

                issue(StopReason.PARSING_ERROR)

            if next_url is None:

                return finish(
                    StopReason.PARSING_ERROR
                    if invalid
                    else StopReason.SOURCE_EXHAUSTED
                )

            if self.max_pages is not None and page >= self.max_pages:

                return finish(StopReason.REQUESTED_LIMIT)

            url = next_url
            page += 1

        return finish(StopReason.REQUESTED_LIMIT)
