import re
from decimal import Decimal
from urllib.parse import urljoin
from pathlib import Path

from bs4 import BeautifulSoup
from pydantic import ValidationError

from scrapers.base_scraper import BaseScraper
from scrapers.models import Opportunity


class WuzzufScraper(BaseScraper):



    EMPLOYMENT_MAPPING = {
        "Full Time": "full_time",
        "Part Time": "part_time",
        "Freelance / Project": "freelance",
        "Contract": "contract",
        "Temporary": "temporary"
    }



    WORK_MODE_MAPPING = {
        "On-site": "on_site",
        "Remote": "remote",
        "Hybrid": "hybrid"
    }



    EXPERIENCE_MAPPING = {
        "Entry Level": "entry_level",
        "Experienced": "unknown"
    }



    def __init__(self, html_path: str):

        super().__init__("wuzzuf")
        self.BASE_URL = self.source_config.base_url
        self.html_path = Path(html_path)

    @staticmethod
    def extract_text(element, selector):

        result = element.select_one(selector)

        if result:
            return result.get_text(" ", strip=True)

        return None



    @staticmethod
    def parse_experience_years(raw_value):
        if not raw_value:
            return None, None

        range_match = re.search(
            r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*Yrs?\s+of\s+Exp",
            raw_value,
            re.IGNORECASE
        )

        if range_match:
            return Decimal(range_match.group(1)), Decimal(range_match.group(2))

        minimum_match = re.search(
            r"(\d+(?:\.\d+)?)\s*\+\s*Yrs?\s+of\s+Exp",
            raw_value,
            re.IGNORECASE
        )

        if minimum_match:
            return Decimal(minimum_match.group(1)), None

        return None, None



    @staticmethod
    def get_date_precision(raw_value):
        if not raw_value:
            return None

        if re.fullmatch(
            r"\d+\s+(minute|hour|day|week|month|year)s?\s+ago",
            raw_value,
            re.IGNORECASE
        ):
            return "relative"

        return "unknown"




    def parse_card(self, card):

        title_element = card.select_one(
            "h2.css-s5fwzh a[href]"
        )

        if not title_element:
            self.record_invalid(
                raw_payload={
                    "card_html": str(card)
                },
                error_type="MissingRequiredField",
                error_message="Job title or link is missing"
            )

            return None

        title = title_element.get_text(strip=True)

        source_url = urljoin(
            self.BASE_URL,
            title_element["href"]
        )

        source_id = None

        if "/jobs/p/" in source_url:
            source_id = source_url.split(
                "/jobs/p/", 1
            )[1].split("-")[0]

        organization = self.extract_text(
            card, "a.css-ipsyv7"
        )

        if organization:
            organization = organization.rstrip("- ")

        location = self.extract_text(
            card, "span.css-16x61xq"
        )

        published_raw = self.extract_text(
            card, "div.css-eg55jf, div.css-1jldrig"
        )

        published_precision = self.get_date_precision(published_raw)

        skills = [
            skill.get_text(" ", strip=True).strip("· ")
            for skill in card.select("a.css-5x9pm1")
        ]

        tags = [
            tag.get_text(" ", strip=True)
            for tag in card.select("div.css-5jhz9n a")
        ]

        employment_types = [
            self.EMPLOYMENT_MAPPING[tag]
            for tag in tags
            if tag in self.EMPLOYMENT_MAPPING
        ]

        work_modes = [
            self.WORK_MODE_MAPPING[tag]
            for tag in tags
            if tag in self.WORK_MODE_MAPPING
        ]


        experience_level_raw = None
        categories = []

        metadata_links = card.select(
            "div.css-1rhj4yg a.css-o171kl"
        )

        for link in metadata_links:
            text = link.get_text(" ", strip=True)

            if text.startswith("·"):
                category = text.lstrip("·").strip()

                if category:
                    categories.append(category)

            elif experience_level_raw is None:
                experience_level_raw = text

        experience_level = (
            self.EXPERIENCE_MAPPING.get(
                experience_level_raw, "unknown"
            )
            if experience_level_raw
            else None
        )


        experience_years_raw = None

        for span in card.select("div.css-1rhj4yg span"):
            text = span.get_text(" ", strip=True)

            if re.search(r"\bYrs?\s+of\s+Exp\b", text, re.IGNORECASE):
                experience_years_raw = text.strip("· ")
                break


        experience_min, experience_max = self.parse_experience_years(
            experience_years_raw
        )

        return Opportunity(
            source_name=self.source_name,
            source_opportunity_id=source_id,
            source_url=source_url,
            title=title,
            organization=organization,
            opportunity_type="job",
            location=location,
            employment_types=employment_types or None,
            work_modes=work_modes or None,
            categories=categories or None,
            experience_level=experience_level,
            experience_level_raw=experience_level_raw,
            experience_years_min=experience_min,
            experience_years_max=experience_max,
            required_skills=skills or None,
            published_at_raw=published_raw,
            published_at_precision=published_precision,
            raw_payload={
                "published_raw": published_raw,
                "experience_level_raw": experience_level_raw,
                "experience_years_raw": experience_years_raw,
                "tags": tags,
                "categories": categories,
                "skill_tags": skills,
                "card_html": str(card)
            }
        )

    def parse_html(self, html):

        soup = BeautifulSoup(html, "lxml")

        cards = soup.select(
            "div.css-ghe2tq.e1v1l3u10"
        )

        opportunities = []

        for card in cards:

            try:

                opportunity = self.parse_card(card)

                if opportunity is not None:
                    opportunities.append(opportunity)

            except ValidationError as error:

                title_element = card.select_one(
                    "h2.css-s5fwzh a[href]"
                )

                source_url = None

                if title_element is not None:
                    source_url = urljoin(
                        self.BASE_URL,
                        title_element["href"]
                    )

                self.record_invalid(
                    raw_payload={
                        "card_html": str(card)
                    },
                    error_type="ValidationError",
                    error_message=str(error),
                    source_url=source_url
                )

                continue

        return opportunities

    def scrape(self) -> list[Opportunity]:

        html = self.html_path.read_text(
            encoding="utf-8"
        )

        return self.parse_html(html)