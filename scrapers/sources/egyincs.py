import hashlib
import json

from itertools import count
from datetime import datetime, timezone
from urllib.robotparser import RobotFileParser

import requests

from scrapers.base_scraper import BaseScraper
from scrapers.collection_result import StopReason
from scrapers.incremental_window import (
    IncrementalWindow,
    PaginationEvidence,
)
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
        incremental_window=None,
        persistent_company_cache=None,
    ):

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

        if not 1 <= page_size <= 20:
            raise ValueError("Page size must be 1-20")

        if endpoint not in {"all", "jobs", "lp_course"}:
            raise ValueError("Invalid endpoint")

        super().__init__("egyincs")

        self.max_jobs = max_jobs
        self.page_size = page_size
        self.max_pages = max_pages
        self.endpoint = endpoint

        if incremental_window is not None:

            if not isinstance(
                incremental_window, IncrementalWindow
            ):
                raise TypeError("Invalid incremental window")

            if endpoint == "all":
                raise ValueError(
                    "Incremental collection requires one endpoint"
                )

        self.incremental_window = incremental_window
        self.pagination_evidence = None


        from scrapers.company_cache import CompanyCache

        if (
            persistent_company_cache is not None
            and not isinstance(
                persistent_company_cache,
                CompanyCache,
            )
        ):
            raise TypeError("Invalid persistent company cache")

        self.persistent_company_cache = (
            persistent_company_cache
        )

        self.company_cache = {}
        self.company_access_failures = set()
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

        if self.incremental_window is not None:

            if endpoint != self.endpoint:
                raise ValueError("Incremental endpoint mismatch")

            if page == 1:

                self.pagination_evidence = PaginationEvidence(
                    self.incremental_window,
                    limit,
                    ordering="id_asc",
                )

            elif (
                self.pagination_evidence is None
                or self.pagination_evidence.page_size != limit
            ):
                raise ValueError(
                    "Invalid incremental pagination state"
                )

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
                "_fields": (
                    fields + ",modified_gmt"
                    if self.incremental_window is not None
                    else fields
                ),
                **(
                    {
                        **self.incremental_window.api_params(),
                        "orderby": "id",
                        "order": "asc",
                    }
                    if self.incremental_window is not None
                    else {}
                ),
            },
        )

        try:
            records = response.json()

        except requests.exceptions.JSONDecodeError as exc:

            raise ValueError(
                "Invalid Egyincs API JSON"
            ) from exc

        if not isinstance(records, list):
            raise ValueError(
                "Unexpected Egyincs API response"
            )

        total_pages = response.headers.get(
            "X-WP-TotalPages"
        )

        if total_pages is not None:

            total_pages = int(total_pages)

            if total_pages < 0:

                raise ValueError(
                    "Invalid pagination metadata"
                )

            if records and total_pages < page:

                raise ValueError(
                    "Inconsistent pagination metadata"
                )

        if self.incremental_window is not None:

            total = response.headers.get("X-WP-Total")

            if total is None or total_pages is None:
                raise ValueError(
                    "Missing incremental pagination metadata"
                )

            try:
                self.pagination_evidence.observe(
                    page=page,
                    records=records,
                    total=int(total),
                    total_pages=total_pages,
                )
            except (ValueError, TypeError) as exc:
                import logging

                logging.getLogger("egyincs").warning(
                    "Pagination validation failed | "
                    "Endpoint: %s | Page: %s | Reason: %s",
                    endpoint,
                    page,
                    str(exc),
                )
                raise

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

        if company_id in self.company_access_failures:
            return None

        if company_id in self.company_cache:
            return self.company_cache[company_id]

        persistent = self.persistent_company_cache

        if persistent is not None:

            found, cached_name = persistent.get(
                company_id
            )

            if found:

                self.company_cache[company_id] = (
                    cached_name
                )

                return cached_name

        try:

            response = self.fetch(
                f"company/{company_id}",
                {"_fields": "id,title"},
            )

        except requests.HTTPError as exc:

            if (
                exc.response is not None
                and exc.response.status_code in {401, 403}
            ):

                self.company_access_failures.add(company_id)

                self.stats["company_access_failures"] = (
                    self.stats.get("company_access_failures", 0) + 1
                )

                self.logger.warning(
                    "Company enrichment unavailable | "
                    "Company ID: %s | HTTP: %s",
                    company_id,
                    exc.response.status_code,
                )

                return None

            if (
                exc.response is not None
                and exc.response.status_code == 404
            ):

                self.company_cache[company_id] = None

                if persistent is not None:

                    persistent.put(company_id, None)

                return None

            raise

        try:

            data = response.json()

        except requests.exceptions.JSONDecodeError as exc:

            raise ValueError(
                "Invalid Egyincs API JSON"
            ) from exc

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

        if persistent is not None and name:

            persistent.put(company_id, name)

        return name

    def report_endpoint(
        self,
        endpoint,
        reason,
        opportunities,
        *,
        pages,
    ):

        completed = reason in {
            StopReason.SOURCE_EXHAUSTED,
            StopReason.REQUESTED_LIMIT,
        }

        self.stats["endpoint_results"][endpoint] = {
            "completed": completed,
            "stop_reason": reason.value,
            "accepted": len(opportunities),
            "pages": pages,
        }

        if not completed and self._running:

            self.mark_collection_issue(reason)

        return opportunities

    def collect_endpoint(
        self,
        endpoint,
        limit,
        seen_ids,
    ):

        opportunities = []
        page_size = (
            self.page_size
            if limit is None
            else min(self.page_size, limit)
        )

        pages = 0
        seen_pages = set()

        def finish(reason):

            return self.report_endpoint(
                endpoint,
                reason,
                opportunities,
                pages=pages,
            )

        page_iterator = (
            count(1)
            if self.max_pages is None
            else range(1, self.max_pages + 1)
        )

        for page in page_iterator:

            try:

                records, total_pages = self.fetch_page(
                    endpoint,
                    page,
                    page_size,
                )

            except (
                requests.RequestException,
                PermissionError,
            ):

                finish(StopReason.SOURCE_ERROR)

                if not self._running:
                    raise

                if (
                    self.endpoint != "all"
                    and not opportunities
                    and not self.invalid_records
                ):
                    raise

                return opportunities

            except ValueError:

                finish(StopReason.PARSING_ERROR)

                if not self._running:
                    raise

                return opportunities

            pages += 1

            self.stats["pages"] += 1
            self.stats["fetched"] += len(records)

            if not records:

                if (
                    total_pages is not None
                    and total_pages >= page
                ):

                    return finish(
                        StopReason.PARSING_ERROR
                    )

                return finish(
                    StopReason.SOURCE_EXHAUSTED
                )

            record_fingerprints = sorted(
                hashlib.sha256(
                    json.dumps(
                        record,
                        sort_keys=True,
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                for record in records
            )

            page_fingerprint = hashlib.sha256(
                "".join(record_fingerprints).encode("ascii")
            ).hexdigest()

            if page_fingerprint in seen_pages:
                return finish(StopReason.SOURCE_ERROR)

            seen_pages.add(page_fingerprint)

            duplicate_count = 0

            observed_at = datetime.now(timezone.utc)

            for record in records:

                if (
                    limit is not None
                    and len(opportunities) >= limit
                ):
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
                        duplicate_count += 1
                        continue

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
                            "id": (
                                source_id
                                if type(source_id) is int
                                else None
                            ),
                            "endpoint": endpoint,
                        },
                        error_type=type(exc).__name__,
                        error_message="Invalid Egyincs record",
                    )

                    continue

                if endpoint == "jobs":

                    try:

                        company_name = self.fetch_company_name(
                            record.get(
                                "felan-jobs_select_company"
                            )
                        )

                    except (
                        requests.RequestException,
                        PermissionError,
                    ):

                        finish(StopReason.SOURCE_ERROR)

                        if not self._running:
                            raise

                        if (
                            self.endpoint != "all"
                            and not opportunities
                            and not self.invalid_records
                        ):
                            raise

                        return opportunities

                    except ValueError:

                        finish(StopReason.PARSING_ERROR)

                        if not self._running:
                            raise

                        return opportunities

                    company_id = str(
                        record.get("felan-jobs_select_company")
                    ).strip()

                    if company_id in self.company_access_failures:

                        self.stats["company_enrichment_deferred"] += 1

                        opportunity = opportunity.model_copy(
                            update={
                                "raw_payload": {
                                    **opportunity.raw_payload,
                                    "_matchpoint_company_enrichment":
                                        "access_denied",
                                }
                            }
                        )

                    if company_name:

                        opportunity = opportunity.model_copy(
                            update={
                                "organization": company_name
                            }
                        )

                seen_ids.add(source_id)

                opportunities.append(opportunity)

                self.stats["accepted"] += 1
                self.stats[endpoint] += 1

                if opportunity.status == "unknown":

                    self.stats["unknown_status"] += 1

            if (
                limit is not None
                and len(opportunities) >= limit
            ):

                return finish(
                    StopReason.REQUESTED_LIMIT
                )

            if duplicate_count == len(records):

                return finish(
                    StopReason.SOURCE_ERROR
                )

            if total_pages is not None:

                if page >= total_pages:

                    return finish(
                        StopReason.SOURCE_EXHAUSTED
                    )

            elif len(records) < page_size:

                return finish(
                    StopReason.SOURCE_EXHAUSTED
                )

        return finish(
            StopReason.REQUESTED_LIMIT
        )

    def incremental_coverage_verified(self, result):

        evidence = self.pagination_evidence

        return (
            self.incremental_window is not None
            and evidence is not None
            and evidence.boundary_verified
            and result.scope_completed
            and result.source_exhausted
            and result.rejected_count == 0
            and self.stats.get(
                "company_enrichment_deferred", 0
            ) == 0
            and result.accepted_count == evidence.expected_total
            and self.stats.get("duplicates", 0) == 0
            and self.stats.get("unpublished", 0) == 0
        )

    def scrape(self):

        self.pagination_evidence = None

        self.company_cache.clear()
        self.company_access_failures.clear()

        self.stats = {
            "pages": 0,
            "fetched": 0,
            "duplicates": 0,
            "unpublished": 0,
            "invalid": 0,
            "accepted": 0,
            "unknown_status": 0,
            "company_access_failures": 0,
            "company_enrichment_deferred": 0,
            "jobs": 0,
            "lp_course": 0,
            "endpoint_results": {},
        }

        try:

            self.load_robots()

        except (
            requests.RequestException,
            PermissionError,
        ):

            if self._running:

                self.mark_collection_issue(
                    StopReason.SOURCE_ERROR
                )

            raise

        seen_ids = set()
        opportunities = []

        if self.endpoint == "all":

            if self.max_jobs is None:
                plan = [
                    ("jobs", None),
                    ("lp_course", None),
                ]

            else:
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

            if limit is not None and limit <= 0:
                self.report_endpoint(
                    endpoint,
                    StopReason.REQUESTED_LIMIT,
                    [],
                    pages=0,
                )
                continue

            opportunities.extend(
                self.collect_endpoint(
                    endpoint,
                    limit,
                    seen_ids,
                )
            )

        reports = list(
            self.stats["endpoint_results"].values()
        )

        if (
            self._running
            and reports
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
            "Egyincs collection statistics: %s",
            self.stats,
        )

        return opportunities