from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, unquote
from urllib.robotparser import RobotFileParser

import requests

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.collection_result import StopReason
from scrapers.models import Opportunity
from scrapers.sources.forasna_mapper import ForasnaMapper


class ForasnaScraper(BaseScraper):

    BASE_URL = "https://forasna.com"
    SEARCH_PATH = "/وظائف-خالية"
    SEARCH_URL = BASE_URL + SEARCH_PATH
    USER_AGENT = "MATCHPOINT/1.0"

    JOB_SELECTOR = (
        "#search-results-container "
        ".result-wrp h2.job-title a[href]"
    )

    def __init__(
        self,
        max_jobs=20,
        max_pages=10,
    ):
        for name, value in (
            ("max_jobs", max_jobs),
            ("max_pages", max_pages),
        ):
            if value is not None and (
                type(value) is not int or value < 1
            ):
                raise ValueError(
                    f"{name} must be a positive integer or None"
                )

        super().__init__("forasna")

        self.max_jobs = max_jobs
        self.max_pages = max_pages
        self.robots = None
        self.stats = {}

    def load_robots(self):
        response = self.client.get(
            self.BASE_URL + "/robots.txt"
        )

        robots = RobotFileParser()
        robots.parse(response.text.splitlines())

        self.robots = robots

    def check_access(self, url):
        parsed = urlparse(url)

        if (
            parsed.scheme != "https"
            or parsed.netloc != "forasna.com"
        ):
            raise ValueError("Invalid Forasna URL")

        if self.robots is None:
            raise RuntimeError("Robots rules not loaded")

        if not self.robots.can_fetch(
            self.USER_AGENT,
            url,
        ):
            raise PermissionError(
                f"Robots rules disallow URL: {url}"
            )

    def fetch_html(self, url):
        self.check_access(url)

        response = self.client.get(url)

        self.check_access(response.url)

        return response.text

    @classmethod
    def extract_job_links_with_diagnostics(cls, soup):

        links = {}
        invalid_links = 0

        cards = soup.select(
            "#search-results-container .result-wrp"
        )

        for card in cards:

            anchors = card.select(
                "h2.job-title a"
            )

            if not anchors:

                invalid_links += 1
                continue

            for anchor in anchors:

                try:

                    href = anchor.get("href")

                    if not isinstance(href, str) or not href.strip():

                        raise ValueError("Missing job URL")

                    url = ForasnaMapper.extract_source_url(
                        href
                    )

                    source_id = (
                        ForasnaMapper.extract_source_id(url)
                    )

                except (ValueError, TypeError, KeyError):

                    invalid_links += 1
                    continue

                links.setdefault(source_id, url)

        return links, invalid_links

    @classmethod
    def extract_job_links(cls, soup):

        links, _ = cls.extract_job_links_with_diagnostics(
            soup
        )

        return links

    @classmethod
    def extract_next_page(cls, soup):
        node = soup.select_one(
            'link[rel="next"][href]'
        )

        if not node:
            return None

        url = urljoin(cls.BASE_URL, node["href"])
        parsed = urlparse(url)

        if (
            parsed.scheme != "https"
            or parsed.netloc != "forasna.com"
            or unquote(parsed.path) != cls.SEARCH_PATH
        ):
            raise ValueError("Invalid Forasna pagination URL")

        return url

    def scrape(self) -> list[Opportunity]:

        self.stats = {
            "pages": 0,
            "discovered": 0,
            "invalid_links": 0,
            "duplicates": 0,
            "pagination_overlaps": 0,
            "unknown_country": 0,
            "details_fetched": 0,
            "unavailable": 0,
            "non_egyptian": 0,
            "expired": 0,
            "inactive": 0,
            "invalid": 0,
            "accepted": 0,
        }

        opportunities = []

        try:

            self.load_robots()

        except (requests.RequestException, PermissionError):

            if self._running:
                self.mark_collection_issue(
                    StopReason.SOURCE_ERROR
                )

            raise

        seen_ids = set()
        visited_pages = set()

        page_url = self.SEARCH_URL

        while (
            page_url
            and (
                self.max_pages is None
                or self.stats["pages"] < self.max_pages
            )
            and (
                self.max_jobs is None
                or len(opportunities) < self.max_jobs
            )
        ):

            if page_url in visited_pages:
                self.logger.warning(
                    "Repeated pagination URL detected"
                )

                if self._running:
                    self.mark_collection_issue(
                        StopReason.SOURCE_ERROR
                    )

                break

            visited_pages.add(page_url)

            try:

                html = self.fetch_html(page_url)

            except (requests.RequestException, PermissionError):

                if self._running:
                    self.mark_collection_issue(
                        StopReason.SOURCE_ERROR
                    )

                if not opportunities:
                    raise

                break

            except ValueError:

                if self._running:
                    self.mark_collection_issue(
                        StopReason.PARSING_ERROR
                    )

                if not opportunities:
                    raise

                break

            soup = BeautifulSoup(html, "lxml")

            if not soup.select_one(
                "#search-results-container"
            ):
                if self._running:
                    self.mark_collection_issue(
                        StopReason.PARSING_ERROR
                    )

                if opportunities:
                    break

                raise ValueError(
                    "Forasna search container not found"
                )

            links, invalid_links = (
                self.extract_job_links_with_diagnostics(soup)
            )

            self.stats["invalid_links"] += invalid_links

            if invalid_links:

                self.logger.warning(
                    "Forasna invalid job links: %s",
                    invalid_links,
                )

                if self._running:

                    self.mark_collection_issue(
                        StopReason.PARSING_ERROR
                    )

            self.stats["pages"] += 1
            self.stats["discovered"] += len(links)

            self.logger.info(
                "Forasna page %s: %s jobs discovered",
                self.stats["pages"],
                len(links),
            )

            if not links:

                if self._running:

                    if soup.select(
                        "#search-results-container .result-wrp"
                    ) or soup.select_one(
                        'link[rel="next"][href]'
                    ):

                        self.mark_collection_issue(
                            StopReason.PARSING_ERROR
                        )

                    else:

                        self.mark_collection_complete(
                            StopReason.SOURCE_EXHAUSTED
                        )

                break

            overlap = set(links).intersection(seen_ids)

            if overlap:
                self.stats["pagination_overlaps"] += len(overlap)

                self.logger.warning(
                    "Forasna pagination overlap: %s",
                    len(overlap),
                )

                if (
                    self.max_jobs is None
                    and self.max_pages is None
                    and self._running
                ):
                    self.mark_collection_issue(
                        StopReason.SOURCE_ERROR
                    )

            new_ids = 0

            for source_id, job_url in links.items():

                if self.max_jobs is not None and len(opportunities) >= self.max_jobs:
                    break

                if source_id in seen_ids:
                    self.stats["duplicates"] += 1
                    continue

                seen_ids.add(source_id)
                new_ids += 1

                try:
                    detail_html = self.fetch_html(job_url)

                except requests.HTTPError as exc:
                    response = exc.response

                    if (
                        response is not None
                        and response.status_code in {404, 410}
                    ):
                        self.stats["unavailable"] += 1

                        self.logger.warning(
                            "Forasna job unavailable: %s",
                            source_id,
                        )
                        continue

                    if self._running:
                        self.mark_collection_issue(
                            StopReason.SOURCE_ERROR
                        )

                    if not opportunities:
                        raise

                    return opportunities

                except (
                    requests.RequestException,
                    PermissionError,
                ):

                    if self._running:
                        self.mark_collection_issue(
                            StopReason.SOURCE_ERROR
                        )

                    if not opportunities:
                        raise

                    return opportunities

                except ValueError:

                    if self._running:
                        self.mark_collection_issue(
                            StopReason.PARSING_ERROR
                        )

                    if not opportunities:
                        raise

                    return opportunities

                self.stats["details_fetched"] += 1

                observed_at = datetime.now(timezone.utc)

                try:
                    detail_soup = BeautifulSoup(
                        detail_html,
                        "lxml",
                    )

                    posting = (
                        ForasnaMapper.extract_job_posting(
                            detail_soup
                        )
                    )

                    location = posting.get("jobLocation")

                    address = (
                        location.get("address")
                        if isinstance(location, dict)
                        else None
                    )

                    country = (
                        address.get("addressCountry")
                        if isinstance(address, dict)
                        else None
                    )

                    if not isinstance(country, str) or not country.strip():
                        self.stats["unknown_country"] += 1
                        continue

                    if country.strip().upper() != "EG":
                        self.stats["non_egyptian"] += 1
                        continue

                    opportunity = ForasnaMapper.map_job(
                        html=detail_html,
                        source_url=job_url,
                        observed_at=observed_at,
                        soup=detail_soup,
                        posting=posting,
                    )

                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    AttributeError,
                ) as exc:

                    self.stats["invalid"] += 1

                    self.record_invalid(
                        source_url=job_url,
                        raw_payload={
                            "source_id": source_id,
                        },
                        error_type=type(exc).__name__,
                        error_message="Forasna mapping failed",
                    )

                    continue

                if opportunity.status == "expired":
                    self.stats["expired"] += 1
                    continue

                if opportunity.status != "active":
                    self.stats["inactive"] += 1
                    continue

                opportunities.append(opportunity)
                self.stats["accepted"] += 1

            if new_ids == 0:

                if self._running:
                    self.mark_collection_issue(
                        StopReason.SOURCE_ERROR
                    )

                break

            if self.max_jobs is not None and len(opportunities) >= self.max_jobs:

                if self._running:
                    self.mark_collection_complete(
                        StopReason.REQUESTED_LIMIT
                    )

                break

            try:

                page_url = self.extract_next_page(soup)

            except ValueError:

                if self._running:
                    self.mark_collection_issue(
                        StopReason.PARSING_ERROR
                    )

                if not opportunities:
                    raise

                break

            if page_url is None:

                if self._running:
                    self.mark_collection_complete(
                        StopReason.SOURCE_EXHAUSTED
                    )

                break

            if self.max_pages is not None and self.stats["pages"] >= self.max_pages:

                if self._running:
                    self.mark_collection_complete(
                        StopReason.REQUESTED_LIMIT
                    )

                break

        self.logger.info(
            "Forasna collection statistics: %s",
            self.stats,
        )

        return opportunities