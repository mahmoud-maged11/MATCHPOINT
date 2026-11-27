
import json
from html import unescape
import re

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from scrapers.models import Opportunity
from scrapers.utils.dates import (
    normalize_source_datetime,
    resolve_opportunity_status,
)


class BaytMapper:

    BASE_URL = "https://www.bayt.com"

    EMPLOYMENT_TYPES = {
        "FULL_TIME": "full_time",
        "PART_TIME": "part_time",
        "CONTRACTOR": "contract",
        "TEMPORARY": "temporary",
        "FREELANCE": "freelance",
    }

    CAREER_LEVELS = {
        "student/internship": "entry_level",
        "entry level": "entry_level",
        "fresh graduate": "entry_level",
        "fresh graduates": "entry_level",
        "mid career": "mid_level",
        "senior level": "senior",
        "management": "manager",
        "director/head": "executive",
        "executive": "executive",
    }

    SALARY_PERIODS = {
        "HOUR": "hourly",
        "DAY": "daily",
        "WEEK": "weekly",
        "MONTH": "monthly",
        "YEAR": "yearly",
    }

    @staticmethod
    def clean_text(value):

        if not isinstance(value, str):
            return None

        value = unescape(value)
        value = re.sub(r"\s+", " ", value).strip()
        return value or None

    @classmethod
    def html_to_text(cls, value):

        if not isinstance(value, str):
            return None

        soup = BeautifulSoup(value, "html.parser")

        for node in soup.select(
            "script, style, noscript, [hidden]"
        ):
            if not node.decomposed:
                node.decompose()

        return cls.clean_text(
            soup.get_text(" ", strip=True)
        )

    @classmethod
    def extract_job_id(cls, url):

        parsed = urlparse(url)

        if (
            parsed.scheme != "https"
            or parsed.netloc != "www.bayt.com"
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Invalid Bayt job URL")

        match = re.fullmatch(
            r"/en/egypt/jobs/[^/]+-([1-9]\d*)/",
            parsed.path
        )

        if not match:
            raise ValueError("Invalid Bayt job path")

        return match.group(1)

    @classmethod
    def find_job_postings(cls, value):

        if isinstance(value, list):

            for item in value:
                yield from cls.find_job_postings(item)

        elif isinstance(value, dict):

            types = value.get("@type", [])

            if isinstance(types, str):
                types = [types]

            if "JobPosting" in types:
                yield value

            if "@graph" in value:
                yield from cls.find_job_postings(
                    value["@graph"]
                )

    @classmethod
    def extract_job_posting(cls, soup):

        postings = []

        for script in soup.select(
            'script[type="application/ld+json"]'
        ):

            try:
                data = json.loads(script.get_text())

            except json.JSONDecodeError:
                continue

            postings.extend(cls.find_job_postings(data))

        if len(postings) != 1:
            raise ValueError(
                "Expected exactly one JobPosting"
            )

        return postings[0]

    @classmethod
    def extract_html_field(cls, soup, selector):

        node = soup.select_one(selector)

        if node is None:
            return None

        return cls.html_to_text(str(node))

    @classmethod
    def extract_organization(cls, posting):

        organization = posting.get("hiringOrganization")

        if isinstance(organization, dict):
            organization = organization.get("name")

        organization = cls.clean_text(organization)

        if organization and organization.casefold() in {
            "confidential",
            "confidential company",
            "anonymous",
            "undisclosed",
        }:
            return None

        return organization

    @classmethod
    def extract_location(cls, posting):

        locations = posting.get("jobLocation", [])

        if isinstance(locations, dict):
            locations = [locations]

        if not isinstance(locations, list):
            return None

        results = []

        for location in locations:

            if not isinstance(location, dict):
                continue

            address = location.get("address", {})

            if not isinstance(address, dict):
                continue

            country = address.get("addressCountry")

            if isinstance(country, dict):
                country = country.get("name")

            country = cls.clean_text(country)

            if not country or country.casefold() not in {
                "eg", "egy", "egypt", "مصر"
            }:
                continue

            parts = []

            for key in (
                "streetAddress",
                "addressLocality",
                "addressRegion",
            ):

                value = cls.clean_text(address.get(key))

                if not value:
                    continue

                if value.casefold() in {
                    "eg", "egy", "egypt", "مصر"
                }:
                    continue

                if value.casefold() not in {
                    part.casefold() for part in parts
                }:
                    parts.append(value)

            parts.append("Egypt")

            result = ", ".join(parts)

            if result not in results:
                results.append(result)

        return "; ".join(results) if results else None

    @classmethod
    def extract_employment_types(cls, posting):

        values = posting.get("employmentType", [])

        if isinstance(values, str):
            values = [values]

        if not isinstance(values, list):
            return None

        result = []

        for value in values:

            if not isinstance(value, str):
                continue

            mapped = cls.EMPLOYMENT_TYPES.get(
                value.strip().upper()
            )

            if mapped and mapped not in result:
                result.append(mapped)

        return result or None

    @classmethod
    def extract_opportunity_type(cls, posting, title):

        values = posting.get("employmentType", [])

        if isinstance(values, str):
            values = [values]

        if not isinstance(values, list):
            values = []

        if any(
            isinstance(value, str)
            and value.upper() in {"INTERN", "INTERNSHIP"}
            for value in values
        ):
            return "internship"

        if re.search(
            r"\b(?:intern|internship)\b",
            title,
            re.IGNORECASE
        ):
            return "internship"

        return "job"

    @classmethod
    def extract_work_modes(cls, posting):

        value = posting.get("jobLocationType")

        if isinstance(value, str):
            value = value.strip().upper()

            if value == "TELECOMMUTE":
                return ["remote"]

        return None

    @classmethod
    def extract_experience(cls, posting, raw):

        minimum = None
        maximum = None

        if raw:

            text = raw.casefold().replace("–", "-")
            text = text.replace("—", "-")

            match = re.fullmatch(
                r"(\d+(?:\.\d+)?)\s*"
                r"(?:-|to)\s*"
                r"(\d+(?:\.\d+)?)\s*years?",
                text
            )

            if match:
                minimum = Decimal(match.group(1))
                maximum = Decimal(match.group(2))

                if minimum <= maximum:
                    return minimum, maximum

                minimum = maximum = None

            match = re.fullmatch(
                r"(\d+(?:\.\d+)?)\s*\+\s*years?",
                text
            )

            if match:
                return Decimal(match.group(1)), None

        experience = posting.get(
            "experienceRequirements", {}
        )

        if isinstance(experience, dict):

            months = experience.get("monthsOfExperience")

            try:

                if months is not None and not isinstance(
                    months, bool
                ):

                    months = Decimal(str(months))

                    if months.is_finite() and months >= 0:
                        minimum = months / Decimal("12")

            except (InvalidOperation, ValueError):
                pass

        return minimum, maximum

    @classmethod
    def extract_education(cls, posting, html_value):

        if html_value:
            return html_value

        education = posting.get("educationRequirements")

        if isinstance(education, dict):
            return cls.clean_text(
                education.get("credentialCategory")
            )

        return cls.clean_text(education)

    @classmethod
    def extract_salary(cls, posting):

        salary = posting.get("baseSalary")

        empty = (None, None, None, None)

        if not isinstance(salary, dict):
            return empty

        currency = cls.clean_text(salary.get("currency"))

        if not currency:
            return empty

        import pycountry

        currency = currency.upper()

        if pycountry.currencies.get(
            alpha_3=currency
        ) is None:
            return empty

        value = salary.get("value")

        if not isinstance(value, dict):
            return empty

        def amount(number):

            if number is None or isinstance(number, bool):
                return None

            try:
                result = Decimal(str(number))

                if result.is_finite() and result > 0:
                    return result

            except (InvalidOperation, ValueError):
                pass

            return None

        minimum = amount(value.get("minValue"))
        maximum = amount(value.get("maxValue"))

        if minimum is None and maximum is None:

            fixed = amount(value.get("value"))
            minimum = maximum = fixed

        if minimum is None and maximum is None:
            return empty

        if (
            minimum is not None
            and maximum is not None
            and minimum > maximum
        ):
            return empty

        unit = value.get("unitText")

        period = None

        if isinstance(unit, str):
            period = cls.SALARY_PERIODS.get(
                unit.upper().strip()
            )

        return minimum, maximum, currency, period

    @classmethod
    def extract_application_status(cls, soup):

        button = soup.select_one("#applyLink_1")

        if button is None:
            return "unknown", None

        text = cls.clean_text(
            button.get_text(" ", strip=True)
        )

        if not text:
            return "unknown", None

        normalized = text.casefold()

        if normalized in {
            "job expired",
            "expired",
            "applications closed",
            "job closed",
            "no longer accepting applications",
        }:
            status = (
                "expired"
                if "expired" in normalized
                else "closed"
            )

            return status, text

        classes = set(button.get("class", []))

        if (
            button.has_attr("disabled")
            or button.get("aria-disabled") == "true"
            or classes.intersection(
                {"disabled", "is-disabled"}
            )
        ):
            return "unknown", text

        if normalized in {
            "easy apply",
            "apply now",
            "apply on company site",
        }:
            return "active", text

        return "unknown", text

    @classmethod
    def map_job(
        cls,
        url,
        html,
        listing=None,
        observed_at=None,
    ):

        observed_at = observed_at or datetime.now(
            timezone.utc
        )

        listing = listing or {}

        job_id = cls.extract_job_id(url)

        soup = BeautifulSoup(html, "html.parser")

        posting = cls.extract_job_posting(soup)

        title = cls.clean_text(posting.get("title"))

        if not title:
            raise ValueError("Missing job title")

        location = cls.extract_location(posting)

        if not location:
            return None

        description = cls.extract_html_field(
            soup,
            '[data-jb-field="description"]'
        )

        if not description:
            description = cls.html_to_text(
                posting.get("description")
            )

        skills = cls.extract_html_field(
            soup,
            '[data-jb-field="skills"]'
        )

        experience_raw = cls.extract_html_field(
            soup,
            '[data-automation-id="data_Years_of_experience"]'
        )

        career_raw = cls.extract_html_field(
            soup,
            '[data-automation-id="data_Career_level"]'
        )

        education_raw = cls.extract_html_field(
            soup,
            '[data-automation-id="data_Degree"]'
        )

        major = cls.extract_html_field(
            soup,
            '[data-automation-id="data_Major"]'
        )

        residence = cls.extract_html_field(
            soup,
            '[data-automation-id="data_Residence_location"]'
        )

        minimum_exp, maximum_exp = cls.extract_experience(
            posting,
            experience_raw
        )

        career_level = None

        if career_raw:
            career_level = cls.CAREER_LEVELS.get(
                career_raw.casefold(),
                "unknown"
            )

        requirements = []

        if skills:
            requirements.append(skills)

        if major:
            requirements.append(f"Major: {major}")

        if residence:
            requirements.append(
                f"Preferred residence: {residence}"
            )

        (
            salary_min,
            salary_max,
            salary_currency,
            salary_period,
        ) = cls.extract_salary(posting)

        published_raw = cls.clean_text(
            posting.get("datePosted")
        )

        deadline_raw = cls.clean_text(
            posting.get("validThrough")
        )

        published_at, published_precision = (
            normalize_source_datetime(published_raw)
        )

        deadline, deadline_precision = (
            normalize_source_datetime(deadline_raw)
        )

        status, status_raw = cls.extract_application_status(
            soup
        )

        status = resolve_opportunity_status(
            status,
            deadline_raw,
            observed_at
        )

        identifier = posting.get("identifier")

        identifier_value = None

        if isinstance(identifier, dict):
            identifier_value = identifier.get("value")

        raw_payload = {
            "url_job_id": job_id,
            "identifier_value": identifier_value,
            "employment_type": posting.get(
                "employmentType"
            ),
            "job_location_type": posting.get(
                "jobLocationType"
            ),
            "experience_requirements": posting.get(
                "experienceRequirements"
            ),
            "education_requirements": posting.get(
                "educationRequirements"
            ),
            "direct_apply": posting.get("directApply"),
            "total_job_openings": posting.get(
                "totalJobOpenings"
            ),
            "applicant_location_requirements": posting.get(
                "applicantLocationRequirements"
            ),
            "is_aggregated": listing.get("is_aggregated"),
            "is_external": listing.get("is_external"),
            "experience_raw": experience_raw,
            "career_level_raw": career_raw,
            "major": major,
            "preferred_residence": residence,
            "status_raw": status_raw,
        }

        return Opportunity(
            source_name="bayt",
            source_opportunity_id=job_id,
            source_url=url,
            title=title,
            organization=cls.extract_organization(posting),
            opportunity_type=cls.extract_opportunity_type(
                posting, title
            ),
            description=description,
            requirements="\n".join(requirements) or None,
            required_skills=None,
            location=location,
            employment_types=cls.extract_employment_types(
                posting
            ),
            work_modes=cls.extract_work_modes(posting),
            experience_level=career_level,
            experience_level_raw=career_raw,
            experience_years_min=minimum_exp,
            experience_years_max=maximum_exp,
            education_level=cls.extract_education(
                posting, education_raw
            ),
            salary_min=salary_min,
            salary_max=salary_max,
            currency=salary_currency,
            salary_period=salary_period,
            published_at=published_at,
            published_at_raw=published_raw,
            published_at_precision=published_precision,
            deadline=deadline,
            deadline_raw=deadline_raw,
            deadline_precision=deadline_precision,
            status=status,
            source_status_raw=status_raw,
            raw_payload=raw_payload,
        )
