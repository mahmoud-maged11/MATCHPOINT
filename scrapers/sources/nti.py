
import re
import requests

from urllib.parse import urljoin, urlparse, parse_qs
from urllib.robotparser import RobotFileParser

from scrapers.base_scraper import BaseScraper
from scrapers.collection_result import StopReason
from scrapers.sources.nti_mapper import NTIMapper


class NTIScraper(BaseScraper):

    BASE_URL = "https://www.nti.sci.eg"
    USER_AGENT = "MATCHPOINT/1.0"

    DISCOVERY = (
        ("hire_ready", "/dey/cat4m.php", "courses4m.php", "catID"),
        ("upskilling", "/dey/catev.php", "coursesev.php", "catID"),
        ("creativa", "/dey/catcrloc.php", "coursescrloc.php", "centerID"),
    )

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

        super().__init__("nti")

        self.max_jobs = max_jobs
        self.max_pages = max_pages

        self.robots = None
        self.detail_cache = {}
        self.career_html = None
        self.stats = {}

    @classmethod
    def validate_url(cls, url):

        parsed = urlparse(url)

        if (
            parsed.scheme != "https"
            or parsed.netloc != "www.nti.sci.eg"
            or parsed.fragment
        ):
            raise ValueError("Invalid NTI URL")

        return url

    def load_robots(self):

        url = self.BASE_URL + "/robots.txt"

        self.robots = RobotFileParser()

        try:
            response = self.client.get(url)

        except requests.HTTPError as exc:

            if (
                exc.response is not None
                and exc.response.status_code in (404, 410)
            ):

                self.robots.parse([
                    "User-agent: *",
                    "Disallow:",
                ])

                self.stats["robots_status"] = (
                    exc.response.status_code
                )

                return

            raise

        self.validate_url(response.url)

        if response.url != url:
            raise PermissionError("Unexpected robots redirect")

        if response.status_code != 200:
            raise PermissionError("Robots policy requires review")

        self.robots.parse(response.text.splitlines())

        self.stats["robots_status"] = response.status_code

    def fetch_html(self, url):

        self.validate_url(url)

        if self.robots is None:
            raise RuntimeError("Robots policy not loaded")

        if not self.robots.can_fetch(self.USER_AGENT, url):
            raise PermissionError(f"Robots denied: {url}")

        response = self.client.get(url)

        self.validate_url(response.url)

        if response.url != url:
            raise PermissionError("Unexpected NTI redirect")

        if response.status_code != 200:
            raise ValueError("Unexpected NTI response")

        return response.content.decode("utf-8-sig")

    @classmethod
    def extract_listing_pages_with_diagnostics(
        cls,
        html,
        discovery_url,
        endpoint,
        parameter,
    ):

        soup = NTIMapper.clean_soup(html)

        pages = {}
        invalid = 0

        for anchor in soup.select(
            ".trackLinks a, .courseLinks a"
        ):

            href = anchor.get("href")

            if not isinstance(href, str) or not href.strip():

                invalid += 1
                continue

            target = urljoin(discovery_url, href)

            try:
                cls.validate_url(target)
            except ValueError:
                invalid += 1
                continue

            parsed = urlparse(target)

            if parsed.path != f"/dey/{endpoint}":
                invalid += 1
                continue

            params = parse_qs(parsed.query)
            values = params.get(parameter, [])

            if (
                len(values) != 1
                or not re.fullmatch(r"[1-9]\d*", values[0])
            ):
                invalid += 1
                continue

            page_id = values[0]

            label = NTIMapper.clean_text(
                anchor.get_text(" ", strip=True)
            )

            if not label:
                invalid += 1
                continue

            pages[page_id] = {
                "page_id": page_id,
                "label": label,
                "url": (
                    cls.BASE_URL
                    + f"/dey/{endpoint}?{parameter}={page_id}"
                ),
            }

        return list(pages.values()), invalid

    @classmethod
    def extract_listing_pages(
        cls, html, discovery_url, endpoint, parameter
    ):

        pages, _ = cls.extract_listing_pages_with_diagnostics(
            html, discovery_url, endpoint, parameter
        )

        return pages

    @classmethod
    def extract_courses_with_diagnostics(cls, html, initiative, page):

        soup = NTIMapper.clean_soup(html)

        courses = []
        invalid = 0

        for anchor in soup.select(
            ".courseLinks a"
        ):

            track_id = anchor.get("data-target", "").strip()

            if not re.fullmatch(r"[1-9]\d*", track_id):
                invalid += 1
                continue

            closed_node = anchor.select_one("span.closed")

            status_raw = (
                NTIMapper.clean_text(
                    closed_node.get_text(" ", strip=True)
                )
                if closed_node is not None
                else None
            )

            closed = bool(
                status_raw
                and re.search(
                    r"registration\s+closed",
                    status_raw,
                    re.IGNORECASE
                )
            )

            if closed_node is not None:
                closed_node.decompose()

            title = NTIMapper.clean_text(
                anchor.get_text(" ", strip=True)
            )

            if not title:
                invalid += 1
                continue

            is_creativa = initiative == "creativa"

            courses.append({
                "initiative": initiative,
                "track_id": track_id,
                "title": title,
                "category": (
                    None if is_creativa else page["label"]
                ),
                "center_id": (
                    page["page_id"] if is_creativa else None
                ),
                "location": (
                    page["label"] if is_creativa else None
                ),
                "closed": closed,
                "status_raw": status_raw,
                "source_url": page["url"],
            })

        return courses, invalid

    @classmethod
    def extract_courses(cls, html, initiative, page):

        courses, _ = cls.extract_courses_with_diagnostics(
            html, initiative, page
        )

        return courses

    def fetch_detail(self, track_id):

        if track_id in self.detail_cache:

            self.stats["cache_hits"] += 1

            return self.detail_cache[track_id]

        if not re.fullmatch(r"[1-9]\d*", track_id):
            raise ValueError("Invalid NTI track ID")

        url = (
            self.BASE_URL
            + f"/dey/pages/modules/{track_id}.html"
        )

        html = self.fetch_html(url)

        self.detail_cache[track_id] = html
        self.stats["details_fetched"] += 1

        return html

    def fetch_career_details(self):

        if self.career_html is None:

            self.career_html = self.fetch_html(
                self.BASE_URL
                + "/dey/pages/modules/careerDev4m.html"
            )

            self.stats["career_details_fetched"] += 1

        return self.career_html

    def collect_course(self, listing):

        try:

            html = self.fetch_detail(listing["track_id"])

        except requests.HTTPError as exc:

            if (
                exc.response is not None
                and exc.response.status_code in (404, 410)
            ):

                self.stats["unavailable"] += 1
                return None

            raise

        career_html = None

        if listing["initiative"] == "hire_ready":

            career_html = self.fetch_career_details()

        try:

            opportunity = NTIMapper.map_course(
                listing,
                html,
                career_html=career_html,
            )

        except (ValueError, TypeError) as exc:

            self.stats["invalid"] += 1

            # Do not retain a failed detail in the cache.
            self.detail_cache.pop(
                listing["track_id"], None
            )

            self.record_invalid(
                raw_payload=listing,
                error_type=type(exc).__name__,
                error_message="Invalid NTI course details",
                source_url=listing["source_url"],
            )

            return None

        self.stats["accepted"] += 1
        self.stats[opportunity.status] += 1
        self.stats[listing["initiative"]] += 1

        return opportunity

    def scrape(self):

        self.detail_cache.clear()
        self.career_html = None

        self.stats = {
            "robots_status": None,
            "discovery_pages": 0,
            "listing_pages": 0,
            "courses_discovered": 0,
            "details_fetched": 0,
            "career_details_fetched": 0,
            "cache_hits": 0,
            "duplicates": 0,
            "identity_conflicts": 0,
            "unavailable": 0,
            "invalid": 0,
            "invalid_discovery_links": 0,
            "invalid_course_links": 0,
            "accepted": 0,
            "closed": 0,
            "unknown": 0,
            "hire_ready": 0,
            "upskilling": 0,
            "creativa": 0,
            "initiative_results": {},
        }

        opportunities = []
        seen = set()
        seen_signatures = {}
        queues = []

        reports = self.stats["initiative_results"]

        for initiative, _, _, _ in self.DISCOVERY:

            reports[initiative] = {
                "discovered": 0,
                "processed": 0,
                "listing_pages_fetched": 0,
                "courses_discovered": 0,
                "courses_attempted": 0,
                "courses_duplicate": 0,
                "accepted": 0,
                "issues": [],
                "stop_reason": "not_started",
            }

        def issue(initiative, reason):

            report = reports[initiative]

            if reason.value not in report["issues"]:

                report["issues"].append(reason.value)

            report["stop_reason"] = reason.value

            if self._running:

                self.mark_collection_issue(reason)

        def finish(reason):

            for report in reports.values():

                if not report["issues"]:

                    if report["stop_reason"] == "not_started":
                        continue

                    report["stop_reason"] = (
                        StopReason.SOURCE_EXHAUSTED.value
                        if report["processed"] == report["discovered"]
                        and reason != StopReason.SOURCE_ERROR
                        else reason.value
                    )

            if (
                self._running
                and reason in {
                    StopReason.SOURCE_EXHAUSTED,
                    StopReason.REQUESTED_LIMIT,
                }
            ):

                self.mark_collection_complete(reason)

            self.logger.info("NTI stats: %s", self.stats)

            return opportunities

        try:

            self.load_robots()

        except (requests.RequestException, PermissionError):

            if self._running:

                self.mark_collection_issue(
                    StopReason.SOURCE_ERROR
                )

            raise

        except ValueError:

            if self._running:

                self.mark_collection_issue(
                    StopReason.PARSING_ERROR
                )

            raise

        # Discover initiative listing pages.

        for initiative, path, endpoint, parameter in self.DISCOVERY:

            url = self.BASE_URL + path

            try:

                html = self.fetch_html(url)

            except (requests.RequestException, PermissionError):

                issue(initiative, StopReason.SOURCE_ERROR)

                if not self._running:
                    raise

                return finish(StopReason.SOURCE_ERROR)

            except ValueError:

                issue(initiative, StopReason.PARSING_ERROR)

                if not self._running:
                    raise

                continue

            self.stats["discovery_pages"] += 1

            pages, invalid = (
                self.extract_listing_pages_with_diagnostics(
                    html, url, endpoint, parameter
                )
            )

            self.stats["invalid_discovery_links"] += invalid

            reports[initiative]["discovered"] = len(pages)

            if invalid or not pages:

                issue(initiative, StopReason.PARSING_ERROR)

            if not pages:
                continue

            if not reports[initiative]["issues"]:

                reports[initiative]["stop_reason"] = "discovered"

            queues.append((initiative, iter(pages)))

        # Preserve round-robin collection.

        while queues:

            remaining_queues = []

            for initiative, pages in queues:

                if (
                    (self.max_jobs is not None and len(opportunities) >= self.max_jobs)
                    or (self.max_pages is not None and self.stats["listing_pages"] >= self.max_pages)
                ):

                    return finish(StopReason.REQUESTED_LIMIT)

                page = next(pages, None)

                if page is None:
                    continue

                remaining_queues.append((initiative, pages))

                try:

                    html = self.fetch_html(page["url"])

                except (
                    requests.RequestException,
                    PermissionError,
                ):

                    issue(initiative, StopReason.SOURCE_ERROR)

                    if not self._running:
                        raise

                    return finish(StopReason.SOURCE_ERROR)

                except ValueError:

                    issue(initiative, StopReason.PARSING_ERROR)

                    if not self._running:
                        raise

                    continue

                self.stats["listing_pages"] += 1
                reports[initiative]["listing_pages_fetched"] += 1

                courses, invalid = (
                    self.extract_courses_with_diagnostics(
                        html, initiative, page
                    )
                )

                self.stats["invalid_course_links"] += invalid
                self.stats["courses_discovered"] += len(courses)
                reports[initiative]["courses_discovered"] += len(courses)

                if invalid or not courses:

                    issue(initiative, StopReason.PARSING_ERROR)

                for listing in courses:

                    if (self.max_jobs is not None and len(opportunities) >= self.max_jobs):

                        return finish(
                            StopReason.REQUESTED_LIMIT
                        )

                    identity = (
                        listing["initiative"],
                        listing["track_id"],
                        listing.get("center_id"),
                    )

                    signature = (
                        listing["title"],
                        listing.get("location"),
                        listing.get("closed"),
                    )

                    if identity in seen:

                        self.stats["duplicates"] += 1
                        reports[initiative]["courses_duplicate"] += 1

                        if seen_signatures[identity] != signature:

                            self.stats["identity_conflicts"] += 1
                            issue(
                                initiative,
                                StopReason.PARSING_ERROR,
                            )

                        continue

                    reports[initiative]["courses_attempted"] += 1

                    try:

                        opportunity = self.collect_course(
                            listing
                        )

                    except (
                        requests.RequestException,
                        PermissionError,
                    ):

                        issue(
                            initiative,
                            StopReason.SOURCE_ERROR,
                        )

                        if not self._running:
                            raise

                        return finish(StopReason.SOURCE_ERROR)

                    except ValueError:

                        issue(
                            initiative,
                            StopReason.PARSING_ERROR,
                        )

                        if not self._running:
                            raise

                        continue

                    if opportunity is not None:

                        seen.add(identity)
                        seen_signatures[identity] = signature

                        opportunities.append(opportunity)

                        reports[initiative]["accepted"] += 1

                reports[initiative]["processed"] += 1

            queues = remaining_queues

            if (self.max_jobs is not None and len(opportunities) >= self.max_jobs):

                return finish(StopReason.REQUESTED_LIMIT)

            if (self.max_pages is not None and self.stats["listing_pages"] >= self.max_pages):

                all_processed = all(
                    report["processed"] == report["discovered"]
                    for report in reports.values()
                )

                return finish(
                    StopReason.SOURCE_EXHAUSTED
                    if all_processed
                    else StopReason.REQUESTED_LIMIT
                )

        return finish(StopReason.SOURCE_EXHAUSTED)
