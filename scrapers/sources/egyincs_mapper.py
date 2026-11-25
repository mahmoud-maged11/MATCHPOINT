import re
from decimal import Decimal, InvalidOperation

import pycountry

from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

from scrapers.models import Opportunity


class EgyincsMapper:
    TYPE_MAPPING = {
        "job": "job",
        "internship": "internship",
        "student-internship": "internship",
        "graduate-internship": "internship",
        "summer-internship": "internship",
        "winter-internship": "internship",
        "graduate-program": "graduate_program",
        "scholarship": "scholarship",
        "volunteer": "volunteering",
        "freelance": "freelance",
        "competition": "competition",
        "hackathon": "hackathon",
        "bootcamp": "training",
        "courses": "training",
        "training": "training",
        "event": "event",
    }

    EMPLOYMENT_MAPPING = {
        "full-time": "full_time",
        "part-time": "part_time",
        "contract": "contract",
        "temporary": "temporary",
        "freelance": "freelance",
    }

    WORK_MODE_MAPPING = {
        "on-site": "on_site",
        "remote": "remote",
        "hybrid": "hybrid",
    }

    EXPERIENCE_MAPPING = {
        "experienced-mid-level": "mid_level",
        "student": "entry_level",
        "fresh-graduate": "entry_level",
        "entry-level": "entry_level",
        "junior": "junior",
        "mid-level": "mid_level",
        "senior": "senior",
        "lead": "lead",
        "manager": "manager",
        "executive": "executive",
    }

    ALLOWED_TAXONOMIES = {
        "jobs-type",
        "jobs-workplace",
        "jobs-career",
        "jobs-experience",
        "jobs-qualification",
        "jobs-categories",
        "jobs-skills",
        "jobs-major",
        "jobs-industry",
        "felan_location",
        "felan_state",
        "course_category",
    }

    @staticmethod
    def clean_html(value):

        if not isinstance(value, str):
            return None

        soup = BeautifulSoup(value, "lxml")

        for element in soup.select("script, style, [hidden]"):
            element.decompose()

        text = soup.get_text(" ", strip=True)

        return " ".join(text.split()) or None

    @classmethod
    def rendered_text(cls, value):

        if isinstance(value, dict):
            return cls.clean_html(value.get("rendered"))

        return cls.clean_html(value)

    @staticmethod
    def unique(values):

        return list(dict.fromkeys(values))

    @classmethod
    def extract_terms(cls, record):

        result = {}

        groups = record.get(
            "_embedded", {}
        ).get("wp:term", [])

        for group in groups:

            if not isinstance(group, list):
                continue

            for term in group:

                if not isinstance(term, dict):
                    continue

                taxonomy = term.get("taxonomy")

                if taxonomy not in cls.ALLOWED_TAXONOMIES:
                    continue

                slug = term.get("slug")
                name = cls.clean_html(term.get("name"))

                if not isinstance(slug, str):
                    continue

                result.setdefault(taxonomy, []).append({
                    "slug": slug,
                    "name": name,
                })

        return result

    @classmethod
    def term_slugs(cls, terms, taxonomy):

        return cls.unique([
            term["slug"]
            for term in terms.get(taxonomy, [])
        ])

    @classmethod
    def term_names(cls, terms, taxonomy):

        return cls.unique([
            term["name"]
            for term in terms.get(taxonomy, [])
            if term["name"]
        ])

    @classmethod
    def map_values(cls, values, mapping):

        if not values:
            return None

        mapped = cls.unique([
            mapping[value]
            for value in values
            if value in mapping
        ])

        return mapped or ["unknown"]

    @classmethod
    def extract_opportunity_type(cls, terms, title, endpoint):

        if endpoint == "lp_course":
            return "training"

        slugs = set(cls.term_slugs(terms, "jobs-type"))

        mapped = {
            cls.TYPE_MAPPING[slug]
            for slug in slugs
            if slug in cls.TYPE_MAPPING
        }

        title_lower = title.casefold()

        graduate_program = re.search(
            r"\bgraduate\s+(?:development\s+|trainee\s+)?"
            r"program(?:me)?\b|"
            r"برنامج\s+تدريب\s+الخريجين",
            title_lower,
        )

        internship_title = re.search(
            r"\b(?:internship|intern|trainee)\b|"
            r"(?:^|\s)تدريب(?:\s|$)",
            title_lower,
        )

        scholarship_title = re.search(
            r"\bscholarship\b|(?:^|\s)منحة(?:\s|$)",
            title_lower,
        )

        event_title = re.search(
            r"\b(?:conference|summit|webinar)\b|"
            r"(?:^|\s)(?:مؤتمر|ندوة)(?:\s|$)",
            title_lower,
        )

        if mapped == {"internship", "scholarship"}:
            if scholarship_title:
                return "scholarship"

        if mapped == {"internship", "graduate_program"}:
            return "graduate_program"

        if mapped == {"job", "freelance"}:
            return "freelance"

        if mapped == {"internship"} and graduate_program:
            return "graduate_program"

        if mapped == {"training"} and event_title:
            return "event"

        if len(mapped) == 1:
            return next(iter(mapped))

        if not mapped:

            if "initiative" in slugs:

                if scholarship_title:
                    return "scholarship"

                if event_title:
                    return "event"

                return "training"

            if "other" in slugs and event_title:
                return "event"

            if not slugs:

                if graduate_program:
                    return "graduate_program"

                if internship_title:
                    return "internship"

                if scholarship_title:
                    return "scholarship"

                if event_title:
                    return "event"

        raise ValueError(
            "Missing or ambiguous opportunity type"
        )

    @classmethod
    def extract_experience(cls, terms):

        slugs = cls.term_slugs(
            terms, "jobs-career"
        )

        names = cls.term_names(
            terms, "jobs-career"
        )

        raw = " | ".join(names) or None

        if not slugs:
            return None, raw

        mapped = {
            cls.EXPERIENCE_MAPPING.get(slug, "unknown")
            for slug in slugs
        }

        if len(mapped) == 1:
            return next(iter(mapped)), raw

        return "unknown", raw

    @classmethod
    def extract_experience_years(cls, terms):

        slugs = cls.term_slugs(
            terms,
            "jobs-experience"
        )

        if len(slugs) != 1:
            return None, None

        slug = slugs[0]

        if slug == "0-exp":
            return 0, None

        if slug == "10":
            return 10, None

        match = re.fullmatch(
            r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)",
            slug,
        )

        if not match:
            return None, None

        minimum = float(match.group(1))
        maximum = float(match.group(2))

        if minimum > maximum:
            return None, None

        return minimum, maximum
    @classmethod
    def extract_location(cls, terms):

        names = cls.unique(
            cls.term_names(terms, "felan_location")
            + cls.term_names(terms, "felan_state")
        )

        return ", ".join(names) or None

    @staticmethod
    def extract_source_url(record, endpoint):

        value = record.get("link")

        if not isinstance(value, str):
            raise ValueError("Missing source URL")

        parsed = urlparse(value)

        expected_path = (
            "/courses/"
            if endpoint == "lp_course"
            else "/opportunities/"
        )

        if (
                parsed.scheme != "https"
                or parsed.netloc != "egyincs.com"
                or not parsed.path.startswith(expected_path)
                or not parsed.path[len(expected_path):].strip("/")
        ):
            raise ValueError("Invalid Egyincs source URL")

        return urlunparse(
            parsed._replace(query="", fragment="")
        )

    @staticmethod
    def extract_published_at(record):

        value = record.get("date_gmt")

        if not isinstance(value, str) or not value.strip():
            return None

        try:
            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(timezone.utc)

        except ValueError:
            return None

    @staticmethod
    def extract_application_url(record):

        value = record.get(
            "felan-jobs_apply_external"
        )

        if not isinstance(value, str):
            return None

        parsed = urlparse(value.strip())

        if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
        ):
            return None

        return urlunparse(
            parsed._replace(fragment="")
        )

    @staticmethod
    def parse_salary_amount(value):

        if value is None:
            return None

        try:

            amount = Decimal(
                str(value).strip().replace(",", "")
            )

        except (InvalidOperation, ValueError):
            return None

        if not amount.is_finite() or amount <= 0:
            return None

        return amount

    @classmethod
    def extract_salary(cls, record):

        display = record.get("felan-jobs_salary_show")

        if display != "range":
            return None, None, None, None

        minimum = cls.parse_salary_amount(
            record.get("felan-jobs_salary_minimum")
        )

        maximum = cls.parse_salary_amount(
            record.get("felan-jobs_salary_maximum")
        )

        if minimum is None and maximum is None:
            return None, None, None, None

        if (
                minimum is not None
                and maximum is not None
                and minimum > maximum
        ):
            return None, None, None, None

        currency_raw = str(
            record.get("felan-jobs_currency_type") or ""
        ).strip()

        currency_mapping = {
            "ج.م": "EGP",
            "جنيه مصري": "EGP",
        }

        currency = currency_mapping.get(
            currency_raw,
            currency_raw.upper(),
        )

        if not pycountry.currencies.get(
                alpha_3=currency
        ):
            currency = None

        periods = {
            "hour": "hourly",
            "day": "daily",
            "week": "weekly",
            "month": "monthly",
            "year": "yearly",
            "project": "project",
        }

        period = periods.get(
            record.get("felan-jobs_salary_rate"),
            "unknown",
        )

        return minimum, maximum, currency, period
    @classmethod
    def map_record(
            cls,
            record,
            endpoint="jobs",
            company_name=None,
            observed_at=None,
    ):

        if endpoint not in {"jobs", "lp_course"}:
            raise ValueError("Unsupported endpoint")

        source_id = record.get("id")

        if (
                type(source_id) is not int
                or source_id <= 0
        ):
            raise ValueError("Invalid source ID")

        if record.get("status") != "publish":
            raise ValueError("Unpublished opportunity")

        title = cls.rendered_text(
            record.get("title")
        )

        if not title:
            raise ValueError("Missing opportunity title")

        description = cls.rendered_text(
            record.get("content")
        )

        source_url = cls.extract_source_url(
            record, endpoint
        )

        terms = cls.extract_terms(record)

        opportunity_type = cls.extract_opportunity_type(
            terms, title, endpoint
        )

        published_at = cls.extract_published_at(record)

        experience_level, experience_raw = (
            cls.extract_experience(terms)
        )

        experience_min, experience_max = (
            cls.extract_experience_years(terms)
        )

        type_slugs = cls.term_slugs(
            terms, "jobs-type"
        )

        employment_types = cls.unique([
            cls.EMPLOYMENT_MAPPING[slug]
            for slug in type_slugs
            if slug in cls.EMPLOYMENT_MAPPING
        ]) or None

        work_modes = cls.map_values(
            cls.term_slugs(terms, "jobs-workplace"),
            cls.WORK_MODE_MAPPING,
        )

        categories = cls.unique(
            cls.term_names(terms, "jobs-categories")
            + cls.term_names(terms, "course_category")
        ) or None

        skills = cls.term_names(
            terms, "jobs-skills"
        ) or None

        if endpoint == "lp_course":
            skills = None

        education = cls.term_names(
            terms, "jobs-qualification"
        )

        majors = cls.term_names(
            terms, "jobs-major"
        )

        application_url = cls.extract_application_url(
            record
        )

        raw_payload = {
            "id": source_id,
            "endpoint": endpoint,
            "title": title,
            "description": description,
            "date_gmt": record.get("date_gmt"),
            "publication_status": record.get("status"),
            "terms": terms,
            "company_id": record.get(
                "felan-jobs_select_company"
            ),
            "application_url": application_url,
            "salary_display": record.get("felan-jobs_salary_show"),
            "salary_minimum": record.get("felan-jobs_salary_minimum"),
            "salary_maximum": record.get("felan-jobs_salary_maximum"),
            "salary_currency": record.get("felan-jobs_currency_type"),
            "salary_rate": record.get("felan-jobs_salary_rate"),
            "closing_date": record.get(
                "felan-jobs_closing_date"
            ),
        }
        salary_min, salary_max, currency, salary_period = (
            cls.extract_salary(record)
        )
        return Opportunity(
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
            salary_period=salary_period,
            source_name="egyincs",
            source_opportunity_id=str(source_id),
            source_url=source_url,
            title=title,
            organization=cls.clean_html(company_name),
            description=description,
            opportunity_type=opportunity_type,
            location=cls.extract_location(terms),
            work_modes=work_modes,
            employment_types=employment_types,
            categories=categories,
            experience_level=experience_level,
            experience_level_raw=experience_raw,
            experience_years_min=experience_min,
            experience_years_max=experience_max,
            education_level=" | ".join(education) or None,
            required_skills=skills,
            requirements=" | ".join(majors) or None,
            published_at=published_at,
            published_at_raw=record.get("date_gmt"),
            published_at_precision=(
                "exact" if published_at else "unknown"
            ),
            deadline=None,
            deadline_raw=cls.clean_html(
                record.get("felan-jobs_closing_date")
            ),
            deadline_precision="unknown",
            collected_at=(
                    observed_at or datetime.now(timezone.utc)
            ),
            status="unknown",
            source_status_raw=record.get("status"),
            raw_payload=raw_payload,
        )
