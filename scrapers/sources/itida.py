import re
from itertools import count
import requests

from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.collection_result import StopReason
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
    def extract_program_links_with_diagnostics(cls, html):

        soup = ITIDAMapper.clean_soup(html)

        links = {}
        unsupported = set()

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
                unsupported.add(slug)
                continue

            links.setdefault(slug, url)

        return list(links.values()), sorted(unsupported)

    @classmethod
    def extract_program_links(cls, html):

        links, _ = cls.extract_program_links_with_diagnostics(
            html
        )

        return links

    @classmethod
    def extract_event_links_with_diagnostics(cls, soup):

        links = {}
        invalid = 0

        for card in soup.select("main h4.listingHeader"):

            anchors = card.select("a[href]")

            if not anchors:
                invalid += 1
                continue

            for anchor in anchors:

                try:

                    href = anchor["href"]

                    if not href.strip():
                        raise ValueError("Missing event URL")

                    url = urljoin(cls.EVENTS_URL, href)

                    url = ITIDAMapper.normalize_url(url)

                    page_type, slug = (
                        ITIDAMapper.extract_identity(url)
                    )

                    if page_type != "event":
                        raise ValueError("Invalid event identity")

                except ValueError:

                    invalid += 1
                    continue

                links.setdefault(slug, url)

        return list(links.values()), invalid

    @classmethod
    def extract_event_links(cls, soup):

        links, _ = cls.extract_event_links_with_diagnostics(
            soup
        )

        return links

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

        seen_ids.add(identity)

        self.stats["accepted"] += 1
        self.stats[page_type + "s"] += 1
        self.stats[opportunity.status] += 1

        return opportunity

    def report_scope(self, scope, reason, results):

        completed = reason in {
            StopReason.SOURCE_EXHAUSTED,
            StopReason.REQUESTED_LIMIT,
        }

        self.stats["scope_results"][scope] = {
            "completed": completed,
            "stop_reason": reason.value,
            "accepted": len(results),
        }

        if not completed and self._running:

            self.mark_collection_issue(reason)

        return results

    def collect_programs(self, limit, seen_ids):

        results = []

        def finish(reason):

            return self.report_scope(
                "programs", reason, results
            )

        if limit == 0:

            return finish(StopReason.REQUESTED_LIMIT)

        try:

            html = self.fetch_html(self.PROGRAMS_URL)

        except (requests.RequestException, PermissionError):

            finish(StopReason.SOURCE_ERROR)

            if not self._running:
                raise

            return results

        except ValueError:

            finish(StopReason.PARSING_ERROR)

            if not self._running:
                raise

            return results

        links, unsupported = (
            self.extract_program_links_with_diagnostics(html)
        )

        self.stats["unsupported_programs"] = unsupported

        if unsupported:
            self.logger.warning(
                f"Unclassified ITIDA programs: {unsupported}"
            )

        self.stats["programs_discovered"] = len(links)

        if not links:

            return finish(StopReason.PARSING_ERROR)

        for url in links:

            if limit is not None and len(results) >= limit:

                return finish(StopReason.REQUESTED_LIMIT)

            try:

                opportunity = self.collect_detail(
                    url, seen_ids
                )

            except (
                requests.RequestException,
                PermissionError,
            ):

                finish(StopReason.SOURCE_ERROR)

                if not self._running:
                    raise

                return results

            except ValueError:

                finish(StopReason.PARSING_ERROR)

                if not self._running:
                    raise

                return results

            if opportunity is not None:

                results.append(opportunity)

        return finish(StopReason.SOURCE_EXHAUSTED)

    def collect_events(self, limit, seen_ids):

        results = []
        issue = None

        def finish(reason):

            return self.report_scope(
                "events",
                issue or reason,
                results,
            )

        if limit == 0:

            return finish(StopReason.REQUESTED_LIMIT)

        try:

            html = self.fetch_html(self.EVENTS_URL)

        except (requests.RequestException, PermissionError):

            finish(StopReason.SOURCE_ERROR)

            if not self._running:
                raise

            return results

        except ValueError:

            finish(StopReason.PARSING_ERROR)

            if not self._running:
                raise

            return results

        soup = BeautifulSoup(html, "lxml")
        discovered = set()

        for page in (
            count(1)
            if self.max_pages is None
            else range(1, self.max_pages + 1)
        ):

            self.stats["event_pages"] += 1

            links, invalid = (
                self.extract_event_links_with_diagnostics(
                    soup
                )
            )

            self.stats["invalid_event_links"] += invalid

            if invalid:

                issue = issue or StopReason.PARSING_ERROR

            if not links:

                return finish(StopReason.PARSING_ERROR)

            new_links = []

            for url in links:

                _, slug = ITIDAMapper.extract_identity(url)

                if slug in discovered:

                    self.stats["duplicates"] += 1
                    self.stats["pagination_overlaps"] += 1

                    if (
                        self.max_jobs is None
                        and self.max_pages is None
                    ):
                        issue = issue or StopReason.SOURCE_ERROR

                    continue

                discovered.add(slug)
                new_links.append(url)

            self.stats["events_discovered"] = len(
                discovered
            )

            if not new_links:

                return finish(StopReason.SOURCE_ERROR)

            remaining = (
                None
                if limit is None
                else limit - len(results)
            )

            next_soup = None
            next_checked = False
            pagination_issue = None

            # Preserve ASP.NET listing session state.

            if (
                (
                    self.max_pages is None
                    or page < self.max_pages
                )
                and (
                    remaining is None
                    or len(new_links) < remaining
                )
            ):

                next_checked = True

                try:

                    next_soup = self.fetch_next_event_page(
                        soup, page + 1
                    )

                except (
                    requests.RequestException,
                    PermissionError,
                ):

                    if not self._running:
                        raise

                    pagination_issue = StopReason.SOURCE_ERROR

                except ValueError:

                    if not self._running:
                        raise

                    pagination_issue = StopReason.PARSING_ERROR

            # Never bypass an explicit access denial.
            # A failed prefetch stops further requests.

            if pagination_issue is not None:

                return finish(pagination_issue)

            for url in new_links:

                if limit is not None and len(results) >= limit:

                    return finish(StopReason.REQUESTED_LIMIT)

                try:

                    opportunity = self.collect_detail(
                        url, seen_ids
                    )

                except (
                    requests.RequestException,
                    PermissionError,
                ):

                    finish(StopReason.SOURCE_ERROR)

                    if not self._running:
                        raise

                    return results

                except ValueError:

                    finish(StopReason.PARSING_ERROR)

                    if not self._running:
                        raise

                    return results

                if opportunity is not None:

                    results.append(opportunity)

            if limit is not None and len(results) >= limit:

                return finish(StopReason.REQUESTED_LIMIT)

            if (
                self.max_pages is not None
                and page >= self.max_pages
            ):

                reason = (
                    StopReason.REQUESTED_LIMIT
                    if self.extract_postback(soup, page + 1)
                    else StopReason.SOURCE_EXHAUSTED
                )

                return finish(reason)

            if not next_checked:

                try:

                    next_soup = self.fetch_next_event_page(
                        soup, page + 1
                    )

                except (
                    requests.RequestException,
                    PermissionError,
                ):

                    finish(StopReason.SOURCE_ERROR)

                    if not self._running:
                        raise

                    return results

                except ValueError:

                    finish(StopReason.PARSING_ERROR)

                    if not self._running:
                        raise

                    return results

            if next_soup is None:

                return finish(StopReason.SOURCE_EXHAUSTED)

            soup = next_soup

        return finish(StopReason.REQUESTED_LIMIT)

    def scrape(self):

        self.stats = {
            "programs_discovered": 0,
            "events_discovered": 0,
            "event_pages": 0,
            "pagination_overlaps": 0,
            "unsupported_programs": [],
            "details_fetched": 0,
            "duplicates": 0,
            "unavailable": 0,
            "invalid": 0,
            "invalid_event_links": 0,
            "accepted": 0,
            "programs": 0,
            "events": 0,
            "active": 0,
            "closed": 0,
            "expired": 0,
            "unknown": 0,
            "scope_results": {},
        }

        try:

            self.load_robots()

        except (requests.RequestException, PermissionError):

            if self._running:

                self.mark_collection_issue(
                    StopReason.SOURCE_ERROR
                )

            raise

        seen_ids = set()

        program_limit = (
            None
            if self.max_jobs is None
            else self.max_jobs // 2
        )

        programs = self.collect_programs(
            program_limit, seen_ids
        )

        program_report = self.stats["scope_results"][
            "programs"
        ]

        # Stop source-wide requests after a source error.

        if (
            program_report["stop_reason"]
            == StopReason.SOURCE_ERROR.value
        ):

            return programs

        event_limit = (
            None
            if self.max_jobs is None
            else self.max_jobs - len(programs)
        )

        events = self.collect_events(
            event_limit, seen_ids
        )

        results = programs + events

        reports = list(
            self.stats["scope_results"].values()
        )

        if (
            self._running
            and all(
                report["completed"]
                for report in reports
            )
        ):

            reason = (
                StopReason.REQUESTED_LIMIT
                if any(
                    report["stop_reason"]
                    == StopReason.REQUESTED_LIMIT.value
                    for report in reports
                )
                else StopReason.SOURCE_EXHAUSTED
            )

            self.mark_collection_complete(reason)

        self.logger.info(
            f"ITIDA collection stats: {self.stats}"
        )

        return results
