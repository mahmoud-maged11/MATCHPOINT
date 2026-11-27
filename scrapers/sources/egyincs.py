from datetime import datetime, timezone
from urllib.robotparser import RobotFileParser

import requests

from scrapers.base_scraper import BaseScraper
from scrapers.sources.egyincs_mapper import EgyincsMapper


class EgyincsScraper(BaseScraper):

    BASE_URL = "https://egyincs.com"
    API_URL = BASE_URL + "/wp-json/wp/v2"
    USER_AGENT = "MATCHPOINT/1.0"

    JOB_FIELDS = ",".join([
        "id",
        "title",
        "link",
        "date_gmt",
        "status",
        "content",
        "jobs-type",
        "jobs-career",
        "jobs-experience",
        "jobs-qualification",
        "jobs-categories",
        "jobs-skills",
        "jobs-major",
        "jobs-industry",
        "felan_location",
        "felan_state",
        "jobs-workplace",
        "felan-jobs_select_company",
        "felan-jobs_salary_show",
        "felan-jobs_salary_rate",
        "felan-jobs_currency_type",
        "felan-jobs_salary_minimum",
        "felan-jobs_salary_maximum",
        "felan-jobs_closing_date",
        "felan-jobs_apply_external",
        "_links",
        "_embedded",
    ])
    COURSE_FIELDS = (
        "id,title,link,date_gmt,status,content,"
        "course_category,_links,_embedded"
    )

    def __init__(
        self,
        max_jobs=20,
        page_size=20,
        max_pages=10,
        endpoint="all",
    ):

        if max_jobs <= 0 or max_pages <= 0:
            raise ValueError("Limits must be positive")

        if not 1 <= page_size <= 20:
            raise ValueError("Page size must be 1-20")

        if endpoint not in {"all", "jobs", "lp_course"}:
            raise ValueError("Invalid endpoint")

        super().__init__("egyincs")

        self.max_jobs = max_jobs
        self.page_size = page_size
        self.max_pages = max_pages
        self.endpoint = endpoint

        self.company_cache = {}
        self.stats = {}
        self.robots = None

    def load_robots(self):

        response = self.client.get(
            self.BASE_URL + "/robots.txt"
        )

        self.robots = RobotFileParser()

        self.robots.parse(
            response.text.splitlines()
        )

    def fetch(self, endpoint, params=None):

        url = f"{self.API_URL}/{endpoint}"

        prepared = requests.Request(
            "GET",
            url,
            params=params
        ).prepare()

        if (
            self.robots is None
            or not self.robots.can_fetch(
                self.USER_AGENT,
                prepared.url
            )
        ):
            raise PermissionError(
                "Egyincs API URL disallowed by robots.txt"
            )

        return self.client.get(url, params=params)

    def fetch_page(self, endpoint, page, limit):

        fields = (
            self.JOB_FIELDS
            if endpoint == "jobs"
            else self.COURSE_FIELDS
        )

        response = self.fetch(
            endpoint,
            {
                "per_page": limit,
                "page": page,
                "orderby": "date",
                "order": "desc",
                "_embed": "wp:term",
                "_fields": fields,
            },
        )

        records = response.json()

        if not isinstance(records, list):
            raise ValueError(
                "Unexpected Egyincs API response"
            )

        total_pages = response.headers.get(
            "X-WP-TotalPages"
        )

        if total_pages is not None:
            total_pages = int(total_pages)

        return records, total_pages

    def fetch_company_name(self, company_id):

        if company_id is None:
            return None

        company_id = str(company_id).strip()

        if (
            not company_id.isascii()
            or not company_id.isdigit()
            or int(company_id) <= 0
        ):
            return None

        if company_id in self.company_cache:
            return self.company_cache[company_id]

        try:

            response = self.fetch(
                f"company/{company_id}",
                {"_fields": "id,title"},
            )

        except requests.HTTPError as exc:

            if (
                exc.response is not None
                and exc.response.status_code == 404
            ):
                self.company_cache[company_id] = None
                return None

            raise

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "Unexpected company response"
            )

        if str(data.get("id")) != company_id:
            raise ValueError("Company ID mismatch")

        name = EgyincsMapper.rendered_text(
            data.get("title")
        )

        self.company_cache[company_id] = name

        return name

    def collect_endpoint(
        self,
        endpoint,
        limit,
        seen_ids,
    ):

        opportunities = []

        # Keep page size fixed during pagination.
        page_size = min(self.page_size, limit)

        for page in range(1, self.max_pages + 1):

            records, total_pages = self.fetch_page(
                endpoint,
                page,
                page_size,
            )

            self.stats["pages"] += 1
            self.stats["fetched"] += len(records)

            if not records:
                break

            new_ids = 0

            observed_at = datetime.now(timezone.utc)

            for record in records:

                if len(opportunities) >= limit:
                    break

                source_id = None

                try:

                    if not isinstance(record, dict):
                        raise ValueError("Invalid record")

                    source_id = record.get("id")

                    if (
                        type(source_id) is not int
                        or source_id <= 0
                    ):
                        raise ValueError("Invalid source ID")

                    if source_id in seen_ids:

                        self.stats["duplicates"] += 1
                        continue

                    seen_ids.add(source_id)
                    new_ids += 1

                    if record.get("status") != "publish":

                        self.stats["unpublished"] += 1
                        continue

                    opportunity = EgyincsMapper.map_record(
                        record,
                        endpoint=endpoint,
                        observed_at=observed_at,
                    )

                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    AttributeError,
                ) as exc:

                    self.stats["invalid"] += 1

                    self.record_invalid(
                        raw_payload={
                            "id": source_id,
                            "endpoint": endpoint,
                        },
                        error_type=type(exc).__name__,
                        error_message="Invalid Egyincs record",
                    )

                    continue

                if endpoint == "jobs":

                    company_name = self.fetch_company_name(
                        record.get(
                            "felan-jobs_select_company"
                        )
                    )

                    if company_name:

                        opportunity = opportunity.model_copy(
                            update={
                                "organization": company_name
                            }
                        )

                opportunities.append(opportunity)

                self.stats["accepted"] += 1
                self.stats[endpoint] += 1

                if opportunity.status == "unknown":
                    self.stats["unknown_status"] += 1

            if len(opportunities) >= limit:
                break

            if new_ids == 0:
                break

            if total_pages is not None:

                if page >= total_pages:
                    break

            elif len(records) < page_size:
                break

        return opportunities

    def scrape(self):

        self.company_cache.clear()

        self.stats = {
            "pages": 0,
            "fetched": 0,
            "duplicates": 0,
            "unpublished": 0,
            "invalid": 0,
            "accepted": 0,
            "unknown_status": 0,
            "jobs": 0,
            "lp_course": 0,
        }

        self.load_robots()

        seen_ids = set()
        opportunities = []

        if self.endpoint == "all":

            course_limit = self.max_jobs // 4
            job_limit = self.max_jobs - course_limit

            plan = [
                ("jobs", job_limit),
                ("lp_course", course_limit),
            ]

        else:

            plan = [
                (self.endpoint, self.max_jobs)
            ]

        for endpoint, limit in plan:

            if limit <= 0:
                continue

            opportunities.extend(
                self.collect_endpoint(
                    endpoint,
                    limit,
                    seen_ids,
                )
            )

        self.logger.info(
            "Egyincs collection statistics: %s",
            self.stats,
        )

        return opportunities