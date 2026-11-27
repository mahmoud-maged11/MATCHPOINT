from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from scrapers.models import Opportunity
from scrapers.utils.dates import (
    normalize_source_datetime,
    resolve_opportunity_status
)


class WuzzufMapper:

    BASE_URL = "https://wuzzuf.net/"

    WORK_MODES = {
        "on_site": "on_site",
        "remote": "remote",
        "hybrid": "hybrid"
    }

    EMPLOYMENT_TYPES = {
        "full_time": "full_time",
        "part_time": "part_time",
        "contract": "contract",
        "temporary": "temporary",
        "freelance": "freelance",
        "freelance_project": "freelance"
    }

    EXPERIENCE_LEVELS = {
        "entry level": "entry_level",
        "student": "entry_level",
        "junior": "junior",
        "experienced": "unknown",
        "mid level": "mid_level",
        "senior": "senior",
        "manager": "manager",
        "senior management": "executive"
    }

    SALARY_PERIODS = {
        "per_hour": "hourly",
        "hourly": "hourly",
        "per_day": "daily",
        "daily": "daily",
        "per_week": "weekly",
        "weekly": "weekly",
        "per_month": "monthly",
        "monthly": "monthly",
        "per_year": "yearly",
        "yearly": "yearly",
        "annually": "yearly",
        "per_project": "project",
        "project": "project"
    }

    @staticmethod
    def clean_html(value):

        if not value:
            return None

        soup = BeautifulSoup(value, "lxml")

        for element in soup(["script", "style"]):
            element.decompose()

        return soup.get_text(" ", strip=True) or None

    @staticmethod
    def normalize(value):

        return (
            value.strip()
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
        )

    @staticmethod
    def extract_names(items):

        if items is None:
            return None

        return [
            item["name"]
            for item in items
            if item.get("name")
        ]

    def extract_location(self, attributes):

        location = attributes.get("location") or {}
        parts = []

        for key in ("area", "city", "country"):

            item = location.get(key) or {}
            name = item.get("name")

            if name and name not in parts:
                parts.append(name)

        return ", ".join(parts) or None

    def extract_work_modes(self, attributes):

        arrangement = (
            attributes.get("workplaceArrangement") or {}
        )

        name = arrangement.get("displayedName")

        if not name:
            return None

        return [
            self.WORK_MODES.get(
                self.normalize(name), "unknown"
            )
        ]

    def extract_employment_types(self, attributes):

        items = attributes.get("workTypes")

        if items is None:
            return None

        result = []

        for item in items:

            name = item.get("name")

            if not name:
                continue

            normalized = self.normalize(name)

            if normalized == "internship":
                continue

            result.append(
                self.EMPLOYMENT_TYPES.get(
                    normalized, "unknown"
                )
            )

        known = [
            value for value in result
            if value != "unknown"
        ]

        return known or result or None

    def extract_salary_period(self, salary):

        period = salary.get("period")

        if isinstance(period, dict):
            period = period.get("name")

        if not period:
            return None

        return self.SALARY_PERIODS.get(
            self.normalize(period),
            "unknown"
        )

    def extract_source_url(self, uri, source_id):

        url = urljoin(self.BASE_URL, uri)
        parsed = urlparse(url)

        if (
            parsed.scheme != "https"
            or parsed.netloc != "wuzzuf.net"
        ):
            raise ValueError("Invalid Wuzzuf URL")

        parts = parsed.path.strip("/").split("/")

        valid_path = (
            len(parts) == 3
            and parts[:2] == ["jobs", "p"]
        ) or (
            len(parts) == 2
            and parts[0] == "internship"
        )

        if not valid_path:
            raise ValueError("Invalid opportunity path")

        url_source_id = parts[-1].split("-", 1)[0]

        if url_source_id != source_id:
            raise ValueError("Source ID mismatch")

        return f"https://wuzzuf.net{parsed.path}"

    def map_job(
        self,
        job: dict,
        company_name: str | None = None,
        observed_at: datetime | None = None
    ) -> Opportunity:

        attributes = job["attributes"]

        observed_at = (
            observed_at or datetime.now(timezone.utc)
        )

        slug = attributes.get("slug")
        uri = attributes.get("uri")

        if not slug or not uri:
            raise ValueError("Missing job slug or URI")

        source_id = slug.split("-", 1)[0]

        if not source_id:
            raise ValueError("Missing source ID")

        source_url = self.extract_source_url(
            uri, source_id
        )

        job_type = attributes.get("jobType")

        opportunity_type = {
            "job": "job",
            "internship": "internship"
        }.get(job_type)

        if opportunity_type is None:
            raise ValueError("Unsupported job type")

        career = attributes.get("careerLevel") or {}
        career_name = career.get("name")

        experience_level = (
            self.EXPERIENCE_LEVELS.get(
                career_name.strip().lower(), "unknown"
            )
            if career_name else None
        )

        experience = (
            attributes.get("workExperienceYears") or {}
        )

        preferences = (
            attributes.get("candidatePreferences") or {}
        )

        education = (
            preferences.get("educationLevel") or {}
        ).get("name")

        if education == "Not Specified":
            education = None

        salary_visible = (
            attributes.get("hideSalary") is False
        )

        company_visible = (
            attributes.get("hideCompany") is False
        )

        salary = (
            attributes.get("salary") or {}
            if salary_visible else {}
        )

        currency = salary.get("currency")

        if isinstance(currency, dict):
            currency = currency.get("code")

        salary_period = self.extract_salary_period(
            salary
        )

        source_status = attributes.get("status")

        published_raw = attributes.get("postedAt")
        deadline_raw = attributes.get("expireAt")

        published_at, published_precision = (
            normalize_source_datetime(published_raw)
        )

        deadline, deadline_precision = (
            normalize_source_datetime(deadline_raw)
        )

        status = resolve_opportunity_status(
            source_status,
            deadline_raw,
            observed_at
        )

        if not company_visible:
            company_name = None

        description = self.clean_html(
            attributes.get("description")
        )

        requirements = self.clean_html(
            attributes.get("requirements")
        )

        location = self.extract_location(attributes)

        categories = self.extract_names(
            attributes.get("workRoles")
        )

        skills = self.extract_names(
            attributes.get("keywords")
        )

        # Retain selected opportunity information only.

        raw_attributes = {
            key: attributes[key]
            for key in (
                "title",
                "jobType",
                "status",
                "postedAt",
                "expireAt",
                "hideCompany",
                "hideSalary"
            )
            if key in attributes
        }

        raw_attributes.update({
            "description": description,
            "requirements": requirements,
            "location": location,
            "keywords": skills,
            "workRoles": categories,
            "careerLevel": career_name,
            "educationLevel": education,
            "workExperienceYears": {
                "min": experience.get("min"),
                "max": experience.get("max")
            }
        })

        if salary_visible:

            raw_attributes["salary"] = {
                "min": salary.get("min"),
                "max": salary.get("max"),
                "currency": currency,
                "period": salary_period
            }

        if company_visible:
            raw_attributes["uri"] = uri

        return Opportunity(
            source_name="wuzzuf",
            source_opportunity_id=source_id,
            source_url=source_url,

            title=attributes.get("title"),
            organization=company_name,
            opportunity_type=opportunity_type,

            description=description,
            requirements=requirements,
            location=location,

            work_modes=self.extract_work_modes(
                attributes
            ),

            employment_types=self.extract_employment_types(
                attributes
            ),

            categories=categories,
            required_skills=skills,

            experience_level=experience_level,
            experience_level_raw=career_name,

            experience_years_min=experience.get("min"),
            experience_years_max=experience.get("max"),

            education_level=education,

            salary_min=salary.get("min"),
            salary_max=salary.get("max"),
            currency=currency,
            salary_period=salary_period,

            published_at=published_at,
            published_at_raw=published_raw,
            published_at_precision=published_precision,

            deadline=deadline,
            deadline_raw=deadline_raw,
            deadline_precision=deadline_precision,

            status=status,
            source_status_raw=source_status,
            collected_at=observed_at,

            raw_payload={
                "api_id": job.get("id"),
                "attributes": raw_attributes
            }
        )