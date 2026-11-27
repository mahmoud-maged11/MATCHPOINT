
import re
import requests

from urllib.parse import urljoin, urlparse, parse_qs
from urllib.robotparser import RobotFileParser

from scrapers.base_scraper import BaseScraper
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

        if max_jobs <= 0 or max_pages <= 0:
            raise ValueError("Collection limits must be positive")

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
    def extract_listing_pages(
        cls,
        html,
        discovery_url,
        endpoint,
        parameter,
    ):

        soup = NTIMapper.clean_soup(html)

        pages = {}

        for anchor in soup.select(
            ".trackLinks a[href], .courseLinks a[href]"
        ):

            target = urljoin(
                discovery_url,
                anchor["href"]
            )

            try:
                cls.validate_url(target)
            except ValueError:
                continue

            parsed = urlparse(target)

            if parsed.path != f"/dey/{endpoint}":
                continue

            params = parse_qs(parsed.query)
            values = params.get(parameter, [])

            if (
                len(values) != 1
                or not re.fullmatch(r"[1-9]\d*", values[0])
            ):
                continue

            page_id = values[0]

            label = NTIMapper.clean_text(
                anchor.get_text(" ", strip=True)
            )

            if not label:
                continue

            pages[page_id] = {
                "page_id": page_id,
                "label": label,
                "url": (
                    cls.BASE_URL
                    + f"/dey/{endpoint}?{parameter}={page_id}"
                ),
            }

        return list(pages.values())

    @classmethod
    def extract_courses(cls, html, initiative, page):

        soup = NTIMapper.clean_soup(html)

        courses = []

        for anchor in soup.select(
            ".courseLinks a[data-target]"
        ):

            track_id = anchor.get("data-target", "").strip()

            if not re.fullmatch(r"[1-9]\d*", track_id):
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

            career_html = None

            if listing["initiative"] == "hire_ready":
                career_html = self.fetch_career_details()

            opportunity = NTIMapper.map_course(
                listing,
                html,
                career_html=career_html,
            )

        except requests.HTTPError as exc:

            if (
                exc.response is not None
                and exc.response.status_code in (404, 410)
            ):

                self.stats["unavailable"] += 1
                return None

            raise

        except (ValueError, TypeError) as exc:

            self.stats["invalid"] += 1

            self.record_invalid(
                raw_payload=listing,
                error_type=type(exc).__name__,
                error_message=str(exc),
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
            "unavailable": 0,
            "invalid": 0,
            "accepted": 0,
            "closed": 0,
            "unknown": 0,
            "hire_ready": 0,
            "upskilling": 0,
            "creativa": 0,
        }

        self.load_robots()

        # Discover each initiative before collecting details.
        queues = []

        for initiative, path, endpoint, parameter in self.DISCOVERY:

            url = self.BASE_URL + path

            html = self.fetch_html(url)

            self.stats["discovery_pages"] += 1

            pages = self.extract_listing_pages(
                html,
                url,
                endpoint,
                parameter,
            )

            if not pages:
                raise ValueError(
                    f"No listing pages found for {initiative}"
                )

            queues.append((initiative, iter(pages)))

        opportunities = []
        seen = set()

        # Round-robin listing discovery.
        while (
            queues
            and len(opportunities) < self.max_jobs
            and self.stats["listing_pages"] < self.max_pages
        ):

            remaining_queues = []

            for initiative, pages in queues:

                if (
                    len(opportunities) >= self.max_jobs
                    or self.stats["listing_pages"] >= self.max_pages
                ):
                    break

                page = next(pages, None)

                if page is None:
                    continue

                remaining_queues.append((initiative, pages))

                html = self.fetch_html(page["url"])

                self.stats["listing_pages"] += 1

                courses = self.extract_courses(
                    html,
                    initiative,
                    page,
                )

                self.stats["courses_discovered"] += len(courses)

                for listing in courses:

                    if len(opportunities) >= self.max_jobs:
                        break

                    identity = (
                        listing["initiative"],
                        listing["track_id"],
                        listing.get("center_id"),
                    )

                    if identity in seen:

                        self.stats["duplicates"] += 1
                        continue

                    seen.add(identity)

                    opportunity = self.collect_course(listing)

                    if opportunity is not None:
                        opportunities.append(opportunity)

            queues = remaining_queues

        self.logger.info("NTI stats: %s", self.stats)

        return opportunities
