import json
import re

from datetime import datetime, timezone
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from scrapers.models import Opportunity


class TanqeebMapper:

    BASE_URL = "https://egypt.tanqeeb.com"

    @staticmethod
    def clean_text(value):

        if not isinstance(value, str):
            return None

        return " ".join(value.split()) or None

    @classmethod
    def extract_job_id(cls, url):

        parsed = urlsplit(url)

        if (
            parsed.scheme != "https"
            or parsed.netloc != "egypt.tanqeeb.com"
        ):
            raise ValueError("Invalid Tanqeeb URL")

        match = re.fullmatch(
            r"/ar/jobs-in-egypt/[^/]+/jobs/(\d+)\.html",
            parsed.path
        )

        if not match:
            raise ValueError("Invalid Tanqeeb job path")

        return match.group(1)

    @classmethod
    def extract_structured_data(cls, soup, schema_type):

        results = []

        def walk(value):

            if isinstance(value, dict):

                types = value.get("@type", [])

                if isinstance(types, str):
                    types = [types]

                if isinstance(types, list) and schema_type in types:
                    results.append(value)

                for child in value.values():
                    walk(child)

            elif isinstance(value, list):

                for child in value:
                    walk(child)

        for script in soup.select(
            'script[type="application/ld+json"]'
        ):
            try:
                walk(json.loads(script.get_text()))
            except (ValueError, TypeError):
                continue

        return results

    @staticmethod
    def parse_date(value):

        if not isinstance(value, str) or not value.strip():
            return None, None, "unknown"

        raw = value.strip()

        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return None, raw, "date_only"

        try:
            parsed = datetime.fromisoformat(
                raw.replace("Z", "+00:00")
            )

            if parsed.tzinfo is None:
                return None, raw, "unknown"

            return (
                parsed.astimezone(timezone.utc),
                raw,
                "exact"
            )

        except ValueError:
            return None, raw, "unknown"

    @classmethod
    def extract_location(cls, posting):

        locations = posting.get("jobLocation", [])

        if isinstance(locations, dict):
            locations = [locations]

        if not isinstance(locations, list):
            return None

        for location in locations:

            if not isinstance(location, dict):
                continue

            address = location.get("address", {})

            if not isinstance(address, dict):
                continue

            country = address.get("addressCountry")

            if isinstance(country, dict):
                country = country.get("name")

            if cls.clean_text(country) not in (
                "EG", "Egypt", "مصر"
            ):
                continue

            parts = [
                cls.clean_text(address.get("addressLocality")),
                cls.clean_text(address.get("addressRegion")),
                "Egypt"
            ]

            return ", ".join(
                dict.fromkeys(part for part in parts if part)
            )

        return None

    @classmethod
    def extract_description(cls, posting, soup):

        html = posting.get("description")

        if not isinstance(html, str) or not html.strip():

            element = soup.select_one(".jobDescriptionAlt")

            html = str(element) if element else ""

        document = BeautifulSoup(html, "html.parser")

        for element in document.select("script, style"):
            element.decompose()

        description = document.get_text(
            separator="\n",
            strip=True
        )

        if len(description.strip()) < 10:
            return None, None

        requirements = []

        headings = {
            "qualifications",
            "requirements",
            "job requirements",
            "required qualifications",
            "المتطلبات",
            "المؤهلات",
            "متطلبات الوظيفة"
        }

        for element in document.select(
            "strong, b, h2, h3, h4, p"
        ):

            heading = cls.clean_text(element.get_text())

            if not heading:
                continue

            if heading.casefold().rstrip(":") not in headings:
                continue

            for sibling in element.next_siblings:

                name = getattr(sibling, "name", None)

                if name in (
                    "strong", "b", "h2", "h3", "h4"
                ):
                    break

                if name in ("ul", "ol"):

                    for item in sibling.select("li"):

                        value = cls.clean_text(item.get_text())

                        if value:
                            requirements.append(value)

        requirements = list(dict.fromkeys(requirements))

        return (
            description,
            "\n".join(requirements) or None
        )

    @classmethod
    def extract_employment_types(cls, posting):

        mapping = {
            "FULL_TIME": "full_time",
            "PART_TIME": "part_time",
            "CONTRACTOR": "contract",
            "TEMPORARY": "temporary",
            "FREELANCE": "freelance"
        }

        raw = posting.get("employmentType", [])

        if isinstance(raw, str):
            raw = [raw]

        if not isinstance(raw, list):
            return None

        values = [
            mapping[item.upper()]
            for item in raw
            if isinstance(item, str)
            and item.upper() in mapping
        ]

        return list(dict.fromkeys(values)) or None

    @classmethod
    def validate_canonical(cls, soup, expected_id):

        canonical = soup.select_one(
            'link[rel="canonical"][href]'
        )

        if canonical is None:
            return None

        url = canonical["href"]

        actual_id = cls.extract_job_id(url)

        if actual_id != expected_id:
            raise ValueError("Canonical job ID mismatch")

        return url

    @classmethod
    def extract_metadata(cls, soup):

        metadata = {}

        allowed_labels = {
            "التصنيف": "category",
            "المجال": "industry",
            "توظيف": "employment_type"
        }

        for row in soup.select("div.meta"):

            label = row.select_one("span.text-secondary")
            value = row.select_one("span.text-dark")

            if label is None or value is None:
                continue

            label_text = cls.clean_text(label.get_text())
            value_text = cls.clean_text(value.get_text())

            if label_text in allowed_labels and value_text:
                metadata[allowed_labels[label_text]] = (
                    value_text
                )

        return metadata

    @classmethod
    def extract_work_modes(cls, posting, soup):

        mapping = {
            "في المكتب": "on_site",
            "عن بعد": "remote",
            "هجين": "hybrid"
        }

        tags = [
            cls.clean_text(element.get_text())
            for element in soup.select(".job-tags .job-tag")
        ]

        modes = [
            mapping[tag]
            for tag in tags
            if tag in mapping
        ]

        if posting.get("jobLocationType") == "TELECOMMUTE":
            modes.append("remote")

        return list(dict.fromkeys(modes)) or None

    @classmethod
    def map_job(cls, url, html, observed_at=None):

        job_id = cls.extract_job_id(url)

        observed_at = (
            observed_at or datetime.now(timezone.utc)
        )

        soup = BeautifulSoup(html, "html.parser")

        canonical_url = cls.validate_canonical(
            soup, job_id
        )

        metadata = cls.extract_metadata(soup)

        postings = cls.extract_structured_data(
            soup, "JobPosting"
        )

        if len(postings) != 1:
            raise ValueError(
                "Expected exactly one JobPosting"
            )

        posting = postings[0]

        title = cls.clean_text(posting.get("title"))

        if not title:
            raise ValueError("Missing job title")

        location = cls.extract_location(posting)

        if not location:
            return None

        organization = posting.get("hiringOrganization", {})

        if isinstance(organization, dict):
            organization = cls.clean_text(
                organization.get("name")
            )
        else:
            organization = None

        description, requirements = cls.extract_description(
            posting, soup
        )

        published_at, published_raw, published_precision = (
            cls.parse_date(posting.get("datePosted"))
        )

        deadline, deadline_raw, deadline_precision = (
            cls.parse_date(posting.get("validThrough"))
        )

        status = "unknown"

        if deadline and deadline <= observed_at:
            status = "expired"

        employment_raw = posting.get("employmentType", [])

        opportunity_type = "job"

        if re.search(
            r"\b(intern|internship)\b|تدريب",
            title,
            re.IGNORECASE
        ):
            opportunity_type = "internship"

        work_modes = cls.extract_work_modes(
            posting, soup
        )

        categories = list(dict.fromkeys(
            metadata[key]
            for key in ("category", "industry")
            if metadata.get(key)
        )) or None

        apply_button = soup.select_one("a.apply-btn")

        apply_available = apply_button is not None

        return Opportunity(
            source_name="tanqeeb",
            source_opportunity_id=job_id,
            source_url=canonical_url or url,
            title=title,
            organization=organization,
            description=description,
            requirements=requirements,
            location=location,
            opportunity_type=opportunity_type,
            employment_types=cls.extract_employment_types(
                posting
            ),
            work_modes=work_modes,
            categories=categories,
            published_at=published_at,
            published_at_raw=published_raw,
            published_at_precision=published_precision,
            deadline=deadline,
            deadline_raw=deadline_raw,
            deadline_precision=deadline_precision,
            collected_at=observed_at,
            status=status,
            raw_payload={
                "employment_type": employment_raw,
                "description_missing": description is None,
                "date_posted": published_raw,
                "valid_through": deadline_raw,
                "canonical_verified": canonical_url is not None,
                "category": metadata.get("category"),
                "industry": metadata.get("industry"),
                "employment_type_html": metadata.get(
                    "employment_type"
                ),
                "apply_button_present": apply_available
            }
        )