from datetime import datetime, timezone

from scrapers.base_scraper import BaseScraper

from scrapers.sources.tanqeeb_mapper import TanqeebMapper

from scrapers.sources.tanqeeb_discovery import (
    TanqeebDiscovery
)


class TanqeebSource(BaseScraper):

    def __init__(
        self,
        fetch_listing,
        fetch_detail,
        max_jobs=20,
        max_pages=5
    ):

        if max_jobs <= 0 or max_pages <= 0:
            raise ValueError(
                "Collection limits must be positive"
            )

        super().__init__("tanqeeb")

        self.fetch_listing = fetch_listing
        self.fetch_detail = fetch_detail

        self.max_jobs = max_jobs
        self.max_pages = max_pages

        self.stats = {}

    def scrape(self):

        results = []
        seen_ids = set()
        visited_pages = set()

        observed_at = datetime.now(timezone.utc)

        current_url = TanqeebDiscovery.LISTING_URL

        self.stats = {
            "pages_fetched": 0,
            "discovered": 0,
            "non_egypt": 0,
            "duplicates": 0,
            "invalid_urls": 0,
            "details_fetched": 0,
            "details_missing": 0,
            "invalid_records": 0,
            "expired": 0,
            "accepted": 0
        }

        while (
            current_url
            and current_url not in visited_pages
            and self.stats["pages_fetched"] < self.max_pages
            and len(results) < self.max_jobs
        ):

            visited_pages.add(current_url)

            html = self.fetch_listing(current_url)

            self.stats["pages_fetched"] += 1

            urls, discovery_stats = (
                TanqeebDiscovery.parse_listing(html)
            )

            for key in (
                "discovered",
                "non_egypt",
                "duplicates",
                "invalid_urls"
            ):
                self.stats[key] += discovery_stats[key]

            for url in urls:

                if len(results) >= self.max_jobs:
                    break

                job_id = TanqeebMapper.extract_job_id(url)

                if job_id in seen_ids:
                    self.stats["duplicates"] += 1
                    continue

                seen_ids.add(job_id)

                detail_html = self.fetch_detail(url)

                if detail_html is None:
                    self.stats["details_missing"] += 1
                    continue

                self.stats["details_fetched"] += 1

                try:

                    opportunity = TanqeebMapper.map_job(
                        url,
                        detail_html,
                        observed_at=observed_at
                    )

                    if opportunity is None:
                        self.stats["non_egypt"] += 1
                        continue

                    if opportunity.status == "expired":
                        self.stats["expired"] += 1
                        continue

                    results.append(opportunity)

                except (ValueError, TypeError) as error:

                    self.stats["invalid_records"] += 1

                    self.record_invalid(
                        raw_payload={"job_id": job_id},
                        error_type=type(error).__name__,
                        error_message=str(error),
                        source_url=url
                    )

            current_url = (
                TanqeebDiscovery.extract_next_page(
                    html,
                    current_url
                )
            )

        self.stats["accepted"] = len(results)

        self.logger.info(
            "Tanqeeb collection stats: %s",
            self.stats
        )

        return results