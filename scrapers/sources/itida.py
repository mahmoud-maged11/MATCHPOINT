import re
import requests

from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.sources.itida_mapper import ITIDAMapper


class ITIDAScraper(BaseScraper):

    BASE_URL = "https://itida.gov.eg"

    PROGRAMS_URL = (
        BASE_URL + "/English/Programs/Pages/default.aspx"
    )

    EVENTS_URL = (
        BASE_URL
        + "/English/MediaCenter/Events/Pages/default.aspx"
    )

    USER_AGENT = "MATCHPOINT/1.0"

    def __init__(
        self,
        max_jobs=20,
        max_pages=10
    ):

        if max_jobs < 1:
            raise ValueError("max_jobs must be positive")

        if max_pages < 1:
            raise ValueError("max_pages must be positive")

        super().__init__("itida")

        self.max_jobs = max_jobs
        self.max_pages = max_pages

        self.robots = None
        self.stats = {}

    def load_robots(self):

        response = self.client.get(
            self.BASE_URL + "/robots.txt"
        )

        self.robots = RobotFileParser()

        self.robots.parse(
            response.text.splitlines()
        )

    def check_access(self, url):

        ITIDAMapper.normalize_url(url)

        if self.robots is None:
            raise RuntimeError("Robots not loaded")

        if not self.robots.can_fetch(
            self.USER_AGENT, url
        ):
            raise PermissionError(
                f"Robots denied: {url}"
            )

    def fetch_html(self, url):

        self.check_access(url)

        response = self.client.get(url)

        self.check_access(response.url)

        return response.text

    @classmethod
    def extract_program_links(cls, html):

        soup = ITIDAMapper.clean_soup(html)

        links = {}

        for anchor in soup.select("a[href]"):

            url = urljoin(
                cls.PROGRAMS_URL,
                anchor["href"]
            )

            try:
                url = ITIDAMapper.normalize_url(url)

                page_type, slug = (
                    ITIDAMapper.extract_identity(url)
                )

            except ValueError:
                continue

            if page_type != "program":
                continue

            if slug not in ITIDAMapper.PROGRAM_TYPES:
                continue

            links.setdefault(slug, url)

        return list(links.values())

    @classmethod
    def extract_event_links(cls, soup):

        links = {}

        for anchor in soup.select(
            "main h4.listingHeader a[href]"
        ):

            url = urljoin(
                cls.EVENTS_URL,
                anchor["href"]
            )

            try:
                url = ITIDAMapper.normalize_url(url)

                page_type, slug = (
                    ITIDAMapper.extract_identity(url)
                )

            except ValueError:
                continue

            if page_type == "event":
                links.setdefault(slug, url)

        return list(links.values())

    @staticmethod
    def extract_postback(soup, page):

        selectors = (
            "a.AspNetPagerPagingButtonsClass[href], "
            "a.AspNetPagerPrevNextButtonsClass[href]"
        )

        for anchor in soup.select(selectors):

            if anchor.has_attr("disabled"):
                continue

            match = re.search(
                r"__doPostBack\('([^']+)','([^']+)'\)",
                anchor["href"]
            )

            if not match:
                continue

            target, argument = match.groups()

            if not target.endswith(
                "$_aspNetContentPager"
            ):
                continue

            if argument == str(page):
                return target, argument

        return None

    @classmethod
    def extract_form(cls, soup):

        form = soup.select_one("form#aspnetForm")

        if form is None:
            raise ValueError("ASP.NET form not found")

        action = urljoin(
            cls.EVENTS_URL,
            form.get("action") or cls.EVENTS_URL
        )

        if action != cls.EVENTS_URL:
            raise ValueError("Unexpected form action")

        if form.get("method", "").lower() != "post":
            raise ValueError("Unexpected form method")

        payload = {}

        for node in form.select("input[name]"):

            if node.has_attr("disabled"):
                continue

            kind = node.get("type", "text").lower()

            if kind in {
                "submit", "button", "image",
                "reset", "file", "password"
            }:
                continue

            if kind in {"checkbox", "radio"}:
                if not node.has_attr("checked"):
                    continue

            payload[node["name"]] = node.get(
                "value", ""
            )

        for node in form.select("select[name]"):

            if node.has_attr("disabled"):
                continue

            option = (
                node.select_one("option[selected]")
                or node.select_one("option")
            )

            if option:
                payload[node["name"]] = option.get(
                    "value",
                    option.get_text(strip=True)
                )

        if "__VIEWSTATE" not in payload:
            raise ValueError("VIEWSTATE not found")

        if "__EVENTVALIDATION" not in payload:
            raise ValueError("EVENTVALIDATION not found")

        return payload

    def fetch_next_event_page(self, soup, page):

        postback = self.extract_postback(
            soup, page
        )

        if postback is None:
            return None

        target, argument = postback

        payload = self.extract_form(soup)

        payload["__EVENTTARGET"] = target
        payload["__EVENTARGUMENT"] = argument

        self.check_access(self.EVENTS_URL)

        response = self.client.post(
            self.EVENTS_URL,
            data=payload,
            headers={"Referer": self.EVENTS_URL}
        )

        self.check_access(response.url)

        return BeautifulSoup(
            response.text, "lxml"
        )

    def collect_detail(self, url, seen_ids):

        page_type, slug = (
            ITIDAMapper.extract_identity(url)
        )

        identity = f"{page_type}:{slug}"

        if identity in seen_ids:
            self.stats["duplicates"] += 1
            return None

        seen_ids.add(identity)

        try:
            html = self.fetch_html(url)

        except requests.HTTPError as error:

            response = error.response

            if (
                response is not None
                and response.status_code in {404, 410}
            ):
                self.stats["unavailable"] += 1
                return None

            raise

        self.stats["details_fetched"] += 1

        try:
            opportunity = ITIDAMapper.map_page(
                html, url
            )

        except (ValueError, TypeError) as error:

            self.stats["invalid"] += 1

            self.record_invalid(
                raw_payload={
                    "source_url": url,
                    "page_type": page_type,
                    "slug": slug
                },
                error_type=type(error).__name__,
                error_message=str(error),
                source_url=url
            )

            return None

        self.stats["accepted"] += 1
        self.stats[page_type + "s"] += 1
        self.stats[opportunity.status] += 1

        return opportunity

    def collect_programs(self, limit, seen_ids):

        results = []

        if limit == 0:
            return results

        html = self.fetch_html(
            self.PROGRAMS_URL
        )

        links = self.extract_program_links(html)

        self.stats["programs_discovered"] = len(links)

        for url in links:

            if len(results) >= limit:
                break

            opportunity = self.collect_detail(
                url, seen_ids
            )

            if opportunity is not None:
                results.append(opportunity)

        return results

    def collect_events(self, limit, seen_ids):

        results = []

        if limit == 0:
            return results

        html = self.fetch_html(
            self.EVENTS_URL
        )

        soup = BeautifulSoup(html, "lxml")

        discovered = set()

        for page in range(1, self.max_pages + 1):

            self.stats["event_pages"] += 1

            links = self.extract_event_links(soup)

            if not links:

                if page == 1:
                    raise ValueError(
                        "No event links found"
                    )

                break

            new_links = []

            for url in links:

                _, slug = (
                    ITIDAMapper.extract_identity(url)
                )

                if slug in discovered:
                    self.stats["duplicates"] += 1
                    continue

                discovered.add(slug)
                new_links.append(url)

            self.stats["events_discovered"] = len(
                discovered
            )

            if not new_links:
                break

            # Preserve the listing session and its state
            # before requesting individual detail pages.
            remaining = limit - len(results)

            next_soup = None

            if (
                page < self.max_pages
                and len(new_links) < remaining
            ):
                next_soup = self.fetch_next_event_page(
                    soup, page + 1
                )

            for url in new_links:

                if len(results) >= limit:
                    break

                opportunity = self.collect_detail(
                    url, seen_ids
                )

                if opportunity is not None:
                    results.append(opportunity)

            if len(results) >= limit:
                break

            if page >= self.max_pages:
                break

            if next_soup is None:

                next_soup = self.fetch_next_event_page(
                    soup, page + 1
                )

            if next_soup is None:
                break

            soup = next_soup

        return results

    def scrape(self):

        self.stats = {
            "programs_discovered": 0,
            "events_discovered": 0,
            "event_pages": 0,
            "details_fetched": 0,
            "duplicates": 0,
            "unavailable": 0,
            "invalid": 0,
            "accepted": 0,
            "programs": 0,
            "events": 0,
            "active": 0,
            "closed": 0,
            "expired": 0,
            "unknown": 0
        }

        self.load_robots()

        seen_ids = set()

        program_limit = self.max_jobs // 2

        programs = self.collect_programs(
            program_limit,
            seen_ids
        )

        event_limit = self.max_jobs - len(programs)

        events = self.collect_events(
            event_limit,
            seen_ids
        )

        results = programs + events

        self.logger.info(
            f"ITIDA collection stats: {self.stats}"
        )

        return results