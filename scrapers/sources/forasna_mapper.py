import json
import re
import unicodedata

from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from scrapers.models import Opportunity
from scrapers.utils.dates import (
    normalize_source_datetime,
    resolve_opportunity_status,
)


class ForasnaMapper:

    BASE_URL = "https://forasna.com"

    EXPERIENCE_LEVELS = {
        "طالب": "entry_level",
        "حديث التخرج": "entry_level",
        "بدون خبرة": "entry_level",
        "لا يشترط خبرة": "entry_level",
        "لا يشترط": "entry_level",
        "خبرة متوسطة": "mid_level",
        "خبرة عالية": "senior",
        "مدير / مشرف": "manager",
    }

    EMPLOYMENT_TYPES = {
        "FULL_TIME": "full_time",
        "PART_TIME": "part_time",
        "CONTRACTOR": "contract",
        "TEMPORARY": "temporary",
        "يوم كامل": "full_time",
        "نصف يوم": "part_time",
        "عمل حر": "freelance",
        "موسمية": "temporary",
    }

    ALLOWED_FIELDS = {
        "مستوي الخبرة",
        "مستوى الخبرة",
        "سنين الخبرة",
        "المؤهل المطلوب",
        "الراتب الأساسي",
        "نوع الوظيفة",
        "مجال الوظيفة",
        "تخصص الوظيفة",
        "اللغة الانجليزية",
        "الحاسب الآلي",
        "مايكروسوفت أوفيس",
    }

    @staticmethod
    def clean_text(value):
        if not isinstance(value, str):
            return None

        return " ".join(value.split()) or None

    @staticmethod
    def normalize_numbers(value):
        if not value:
            return ""

        value = "".join(
            char for char in value
            if unicodedata.category(char) != "Cf"
        )

        return value.translate(
            str.maketrans(
                "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
                "01234567890123456789",
            )
        )

    @classmethod
    def extract_source_url(cls, url):
        url = urljoin(cls.BASE_URL, url)
        parsed = urlparse(url)

        if (
            parsed.scheme != "https"
            or parsed.netloc != "forasna.com"
            or not parsed.path.startswith("/job/p/")
        ):
            raise ValueError("Invalid Forasna job URL")

        return f"{cls.BASE_URL}{parsed.path}"

    @classmethod
    def extract_source_id(cls, url):
        url = cls.extract_source_url(url)

        match = re.search(
            r"-([0-9]+)/?$",
            urlparse(url).path,
        )

        if not match:
            raise ValueError("Missing Forasna job ID")

        return match.group(1)

    @staticmethod
    def extract_job_posting(soup):

        def find_posting(data):
            if isinstance(data, list):
                for item in data:
                    result = find_posting(item)

                    if result is not None:
                        return result

            elif isinstance(data, dict):
                if data.get("@type") == "JobPosting":
                    return data

                if "@graph" in data:
                    return find_posting(data["@graph"])

            return None

        for script in soup.select(
            'script[type="application/ld+json"]'
        ):
            try:
                data = json.loads(
                    script.string or script.get_text()
                )
            except (ValueError, TypeError):
                continue

            posting = find_posting(data)

            if posting is not None:
                return posting

        raise ValueError("JobPosting JSON-LD not found")

    @classmethod
    def extract_fields(cls, soup):
        fields = {}

        for label in soup.select("p.title-lable"):
            key = cls.clean_text(
                label.get_text(" ", strip=True)
            )

            if key not in cls.ALLOWED_FIELDS:
                continue

            value = label.parent.select_one("p.item-info")

            if value:
                fields[key] = cls.clean_text(
                    value.get_text(" ", strip=True)
                )

        return fields

    @classmethod
    def extract_description(cls, soup, posting):
        node = soup.select_one(
            ".job-more-info.descri p.job-bio"
        )

        if node:
            for tag in node.select(
                "script, style, [hidden]"
            ):
                tag.decompose()

            description = cls.clean_text(
                node.get_text(" ", strip=True)
            )

            if description:
                return description

        raw = posting.get("description")

        if isinstance(raw, str):
            parsed = BeautifulSoup(raw, "lxml")

            for tag in parsed.select(
                "script, style, [hidden]"
            ):
                tag.decompose()

            return cls.clean_text(
                parsed.get_text(" ", strip=True)
            )

        return None

    @classmethod
    def extract_experience_years(cls, value):

        value = cls.normalize_numbers(value).strip()

        if not value:
            return None, None

        if value in {
            "لا يشترط",
            "لا يشترط خبرة",
            "بدون خبرة",
        }:
            return 0, None

        arabic_numbers = {
            "سنتان": "2",
            "سنتين": "2",
            "سنة": "1",
            "عامان": "2",
            "عامين": "2",
            "عام": "1",
        }

        for word, number in arabic_numbers.items():
            value = re.sub(
                rf"\b{word}\b",
                number,
                value,
            )

        number = r"\d+(?:\.\d+)?"

        match = re.search(
            rf"({number})\s*[-–—]\s*({number})",
            value,
        )

        if match:
            minimum = float(match.group(1))
            maximum = float(match.group(2))

            if minimum <= maximum:
                return minimum, maximum

            return None, None

        numbers = re.findall(number, value)

        if len(numbers) != 1:
            return None, None

        years = float(numbers[0])

        if any(
                phrase in value
                for phrase in [
                    "على الأقل",
                    "علي الأقل",
                    "أكثر من",
                    "اكثر من",
                ]
        ):
            return years, None

        if any(
                phrase in value
                for phrase in [
                    "على الأكثر",
                    "علي الأكثر",
                    "أقل من",
                    "اقل من",
                    "بحد أقصى",
                    "بحد اقصى",
                ]
        ):
            return None, years

        return None, None


    @classmethod
    def extract_salary(cls, fields, posting):
        raw = fields.get("الراتب الأساسي")

        # Explicitly undisclosed salary takes priority.
        if raw and "غير معلن" in raw:
            return None, None, None, None

        salary = posting.get("baseSalary")

        if isinstance(salary, dict):
            value = salary.get("value")
            currency = salary.get("currency")

            if isinstance(value, dict):
                minimum = value.get("minValue")
                maximum = value.get("maxValue")

                if minimum is None and maximum is None:
                    minimum = value.get("value")
                    maximum = minimum

                try:
                    minimum = (
                        float(minimum)
                        if minimum is not None
                        else None
                    )

                    maximum = (
                        float(maximum)
                        if maximum is not None
                        else None
                    )
                except (TypeError, ValueError):
                    minimum = maximum = None

                if minimum == 0 and maximum == 0:
                    return None, None, None, None

                periods = {
                    "HOUR": "hourly",
                    "DAY": "daily",
                    "WEEK": "weekly",
                    "MONTH": "monthly",
                    "YEAR": "yearly",
                }

                period = periods.get(
                    str(value.get("unitText", "")).upper()
                )

                if minimum is not None or maximum is not None:
                    return (
                        minimum,
                        maximum,
                        currency,
                        period,
                    )

        if not raw:
            return None, None, None, None

        normalized = cls.normalize_numbers(raw)
        normalized = normalized.replace(",", "")
        normalized = normalized.replace("٬", "")

        if "جنيه مصري" not in normalized:
            return None, None, None, None

        match = re.search(
            r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)",
            normalized,
        )

        if match:
            minimum = float(match.group(1))
            maximum = float(match.group(2))

            if minimum == 0 and maximum == 0:
                return None, None, None, None

            if minimum > maximum:
                return None, None, None, None

            return minimum, maximum, "EGP", None

        return None, None, None, None

    @classmethod
    def extract_location(cls, posting):
        location = posting.get("jobLocation")

        if not isinstance(location, dict):
            return None

        address = location.get("address")

        if not isinstance(address, dict):
            return None

        parts = [
            cls.clean_text(address.get("addressLocality")),
            cls.clean_text(address.get("addressRegion")),
            cls.clean_text(address.get("addressCountry")),
        ]

        return ", ".join(
            dict.fromkeys(
                part for part in parts if part
            )
        ) or None

    @classmethod
    def extract_organization(cls, posting):
        organization = posting.get("hiringOrganization")

        if not isinstance(organization, dict):
            return None

        name = cls.clean_text(organization.get("name"))

        if name in {
            "شركة غير معلنة",
            "غير معلن",
            "شركة غير معلن عنها",
        }:
            return None

        return name

    @classmethod
    def extract_employment_types(cls, posting, fields):

        raw = posting.get("employmentType")

        if not raw:
            raw = fields.get("نوع الوظيفة")

        if not raw:
            return None

        values = raw if isinstance(raw, list) else [raw]

        values = [
            value for value in values
            if isinstance(value, str)
               and value not in {"INTERN", "تدريب"}
        ]

        if not values:
            return None

        mapped = [
            cls.EMPLOYMENT_TYPES.get(value)
            for value in values
        ]

        known = list(dict.fromkeys(
            value for value in mapped if value
        ))

        return known or ["unknown"]

    @classmethod
    def map_job(
        cls,
        html,
        source_url,
        observed_at=None,
        *,
        soup=None,
        posting=None,
    ):

        observed_at = (
            observed_at or datetime.now(timezone.utc)
        )

        source_url = cls.extract_source_url(source_url)
        source_id = cls.extract_source_id(source_url)

        if soup is None:
            soup = BeautifulSoup(html, "lxml")

        if posting is None:
            posting = cls.extract_job_posting(soup)

        fields = cls.extract_fields(soup)

        identifier = posting.get("identifier")

        if isinstance(identifier, dict):
            identifier = identifier.get("value")

        if identifier is not None:
            if str(identifier) != source_id:
                raise ValueError("Forasna job ID mismatch")

        title = cls.clean_text(posting.get("title"))

        if not title:
            raise ValueError("Missing Forasna job title")

        location = cls.extract_location(posting)
        organization = cls.extract_organization(posting)

        description = cls.extract_description(
            soup,
            posting,
        )

        experience_raw = (
            fields.get("مستوي الخبرة")
            or fields.get("مستوى الخبرة")
        )

        experience_level = (
            cls.EXPERIENCE_LEVELS.get(
                experience_raw,
                "unknown",
            )
            if experience_raw
            else None
        )

        experience_min, experience_max = (
            cls.extract_experience_years(
                fields.get("سنين الخبرة")
            )
        )

        salary_min, salary_max, currency, salary_period = (
            cls.extract_salary(fields, posting)
        )

        published_raw = posting.get("datePosted")
        deadline_raw = posting.get("validThrough")

        published_at, published_precision = (
            normalize_source_datetime(published_raw)
        )

        deadline, deadline_precision = (
            normalize_source_datetime(deadline_raw)
        )

        apply_button = soup.select_one("a.apply-btn")

        source_status_raw = (
            cls.clean_text(
                apply_button.get_text(" ", strip=True)
            )
            if apply_button
            else None
        )

        source_status = (
            "active"
            if source_status_raw == "تقدم للوظيفة"
            else "unknown"
        )

        status = resolve_opportunity_status(
            source_status,
            deadline_raw,
            observed_at,
        )

        # A confirmed past deadline takes priority.
        if deadline and deadline <= observed_at:
            status = "expired"

        categories = [
            fields.get("مجال الوظيفة"),
            fields.get("تخصص الوظيفة"),
        ]

        categories = [
            value for value in categories if value
        ] or None

        requirement_keys = [
            "سنين الخبرة",
            "المؤهل المطلوب",
            "اللغة الانجليزية",
            "الحاسب الآلي",
            "مايكروسوفت أوفيس",
        ]

        requirements = "\n".join(
            f"{key}: {fields[key]}"
            for key in requirement_keys
            if fields.get(key)
        ) or None

        raw_payload = {
            "identifier": source_id,
            "title": title,
            "organization": organization,
            "location": location,
            "description": description,
            "datePosted": published_raw,
            "validThrough": deadline_raw,
            "employmentType": posting.get("employmentType"),
            "baseSalary": posting.get("baseSalary"),
            "fields": fields,
            "application_status": source_status_raw,
        }

        raw_employment = posting.get("employmentType")

        employment_values = (
            raw_employment
            if isinstance(raw_employment, list)
            else [raw_employment]
        )

        return Opportunity(
            source_name="forasna",
            source_opportunity_id=source_id,
            source_url=source_url,
            title=title,
            organization=organization,
            description=description,
            opportunity_type=(
                "internship"
                if (
                        "INTERN" in employment_values
                        or fields.get("نوع الوظيفة") == "تدريب"
                )
                else "freelance"
                if fields.get("نوع الوظيفة") == "عمل حر"
                else "job"
            ),
            location=location,
            work_modes=(
                ["remote"]
                if fields.get("نوع الوظيفة") == "عمل من المنزل"
                else None
            ),
            employment_types=cls.extract_employment_types(
                posting,
                fields,
            ),
            categories=categories,
            experience_level=experience_level,
            experience_level_raw=experience_raw,
            experience_years_min=experience_min,
            experience_years_max=experience_max,
            education_level=fields.get("المؤهل المطلوب"),
            required_skills=None,
            requirements=requirements,
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
            salary_period=salary_period,
            published_at=published_at,
            published_at_raw=published_raw,
            published_at_precision=published_precision,
            deadline=deadline,
            deadline_raw=deadline_raw,
            deadline_precision=deadline_precision,
            collected_at=observed_at,
            status=status,
            source_status_raw=source_status_raw,
            raw_payload=raw_payload,
        )