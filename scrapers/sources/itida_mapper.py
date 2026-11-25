import re

from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

from scrapers.models import Opportunity


class ITIDAMapper:
    BASE_URL = "https://itida.gov.eg"

    PROGRAM_TYPES = {
        "studentsummertraining": "internship",
        "train-to-hire-program": "training",
        "train-to-hire-for-its-bps": "training",
        "train-to-hire-for-electronics": "training",
        "itida-gigs-freelancing-program": "training",
        "itida-dxc-dandelion-training-program": "training",
        "up4jobs-training-program": "training",
        "future-work-is-digital": "training",
        "north-sinai-program": "training"
    }

    EVENT_TYPES = {
        "training": "training",
        "workshop": "training",
        "conference": "event",
        "summit": "event",
        "webinar": "event",
        "employment fair": "event",
        "exhibition": "event",
        "event": "event",
        "matchmaking": "event"
    }

    @staticmethod
    def clean_text(value):

        if not isinstance(value, str):
            return ""

        value = value.replace("\u200b", "")
        value = value.replace("\ufeff", "")

        return " ".join(value.split())

    @classmethod
    def node_text(cls, node):

        if node is None:
            return ""

        return cls.clean_text(
            node.get_text(" ", strip=True)
        )

    @classmethod
    def clean_soup(cls, html):

        soup = BeautifulSoup(html, "lxml")

        for node in soup.select(
                "script, style, noscript, [hidden], "
                "[aria-hidden='true'], input[type='hidden']"
        ):

            if node.decomposed:
                continue

            node.decompose()

        for node in soup.select("[style]"):

            if node.decomposed:
                continue

            style = node.get("style", "")

            if re.search(
                    r"(?:^|;)\s*display\s*:\s*none\b",
                    style,
                    re.IGNORECASE
            ):
                node.decompose()

        return soup

    @classmethod
    def normalize_url(cls, url):

        parsed = urlparse(url)

        if (
                parsed.scheme != "https"
                or parsed.netloc.lower() != "itida.gov.eg"
        ):
            raise ValueError("Invalid ITIDA URL")

        path = parsed.path

        if not path.lower().endswith(".aspx"):
            raise ValueError("Invalid ITIDA page")

        return urlunparse((
            "https",
            "itida.gov.eg",
            path,
            "",
            "",
            ""
        ))

    @classmethod
    def extract_identity(cls, url):

        url = cls.normalize_url(url)

        path = urlparse(url).path.lower()

        program = re.fullmatch(
            r"/english/programs/([^/]+)/pages/default\.aspx",
            path
        )

        if program:
            return "program", program.group(1)

        event = re.fullmatch(
            r"/english/mediacenter/events/pages/([^/]+)\.aspx",
            path
        )

        if event and event.group(1) != "default":
            return "event", event.group(1)

        raise ValueError("Unsupported ITIDA page")

    @classmethod
    def extract_program_sections(cls, root):

        sections = []

        for node in root.select(".ms-rtestate-field"):

            text = cls.node_text(node)

            if text and text not in sections:
                sections.append(text)

        return sections

    @classmethod
    def extract_program_requirements(cls, sections):

        for section in sections:

            match = re.search(
                r"\b(?:Admission criteria|Eligibility)\b"
                r"\s*:?\s*(.+)",
                section,
                re.IGNORECASE
            )

            if not match:
                continue

            requirements = re.split(
                r"\bRegistration\b|"
                r"\bITIDA Gigs Target in Numbers\b",
                match.group(1),
                maxsplit=1,
                flags=re.IGNORECASE
            )[0]

            requirements = cls.clean_text(requirements)

            if requirements:
                return requirements

        return None

    @classmethod
    def extract_program_status(cls, slug, sections):

        text = " ".join(sections)

        if slug == "studentsummertraining":

            systel_closed = re.search(
                r"Systel\s+Program\s*:\s*Closed\b",
                text,
                re.IGNORECASE
            )

            nti_closed = re.search(
                r"NTI\s+programs\s+Registration"
                r"\s*:\s*Closed\b",
                text,
                re.IGNORECASE
            )

            if systel_closed and nti_closed:
                return "closed", (
                    "Systel Program: Closed; "
                    "NTI programs Registration: Closed"
                )

        return "unknown", None

    @classmethod
    def extract_event_fields(cls, root):

        metadata = root.select_one(".EventItemDev")

        if metadata is None:
            raise ValueError("Event metadata not found")

        text = cls.node_text(metadata)

        pattern = (
            r"Start Date\s*:\s*(.*?)"
            r"\s*End Date\s*:\s*(.*?)"
            r"\s*Location\s*:\s*(.*?)"
            r"\s*Category\s*:\s*(.*)"
        )

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if not match:
            return {}

        return {
            "start_date": cls.clean_text(match.group(1)),
            "end_date": cls.clean_text(match.group(2)),
            "location": cls.clean_text(match.group(3)),
            "category": cls.clean_text(match.group(4))
        }

    @staticmethod
    def parse_event_date(value):

        if not isinstance(value, str):
            return None

        match = re.match(
            r"^\s*(\d{1,2}/\d{1,2}/\d{4})",
            value
        )

        if match:

            try:
                return datetime.strptime(
                    match.group(1),
                    "%d/%m/%Y"
                ).date()

            except ValueError:
                return None

        try:
            return datetime.strptime(
                value.strip(),
                "%d %b %Y"
            ).date()

        except ValueError:
            return None

    @classmethod
    def extract_event_status(cls, fields, observed_at):

        end_date = cls.parse_event_date(
            fields.get("end_date")
        )

        start_date = cls.parse_event_date(
            fields.get("start_date")
        )

        if start_date and end_date:
            if end_date < start_date:
                return "unknown", None

        if end_date and end_date < observed_at.date():
            return "expired", "Event end date has passed"

        return "unknown", None

    @classmethod
    def map_program(cls, root, url, slug, observed_at):

        opportunity_type = cls.PROGRAM_TYPES.get(slug)

        if opportunity_type is None:
            raise ValueError("Unsupported program type")

        title = cls.node_text(
            root.select_one("h1.briefHeader")
        )

        if not title:
            title = cls.node_text(
                root.select_one("h1.mainTitle")
            )

        if not title:
            raise ValueError("Program title not found")

        sections = cls.extract_program_sections(root)

        if not sections:
            raise ValueError("Program content not found")

        description = "\n\n".join(sections)

        requirements = cls.extract_program_requirements(
            sections
        )

        status, status_raw = cls.extract_program_status(
            slug, sections
        )

        return Opportunity(
            source_name="itida",
            source_opportunity_id=f"program:{slug}",
            source_url=url,
            title=title,
            organization="ITIDA",
            description=description,
            opportunity_type=opportunity_type,
            requirements=requirements,
            status=status,
            source_status_raw=status_raw,
            collected_at=observed_at,
            raw_payload={
                "page_type": "program",
                "slug": slug,
                "title": title,
                "sections": sections,
                "registration_status": status_raw
            }
        )

    @classmethod
    def map_event(cls, root, url, slug, observed_at):

        title = cls.node_text(
            root.select_one(".EventItemDev h4")
        )

        if not title:
            raise ValueError("Event title not found")

        description = cls.node_text(
            root.select_one(".innerPageContent")
        )

        if not description:
            raise ValueError("Event description not found")

        fields = cls.extract_event_fields(root)

        category = fields.get("category")

        opportunity_type = cls.EVENT_TYPES.get(
            (category or "").lower()
        )

        if opportunity_type is None:
            raise ValueError("Unsupported event category")

        status, status_raw = cls.extract_event_status(
            fields, observed_at
        )

        return Opportunity(
            source_name="itida",
            source_opportunity_id=f"event:{slug}",
            source_url=url,
            title=title,
            organization="ITIDA",
            description=description,
            opportunity_type=opportunity_type,
            location=fields.get("location") or None,
            categories=[category] if category else None,
            status=status,
            source_status_raw=status_raw,
            collected_at=observed_at,
            raw_payload={
                "page_type": "event",
                "slug": slug,
                "title": title,
                "description": description,
                "event_start_date": fields.get("start_date"),
                "event_end_date": fields.get("end_date"),
                "location": fields.get("location"),
                "category": category
            }
        )

    @classmethod
    def map_page(cls, html, url, observed_at=None):

        observed_at = observed_at or datetime.now(
            timezone.utc
        )

        if observed_at.utcoffset() is None:
            raise ValueError("Observation time must be aware")

        observed_at = observed_at.astimezone(timezone.utc)

        url = cls.normalize_url(url)

        page_type, slug = cls.extract_identity(url)

        soup = cls.clean_soup(html)

        root = soup.select_one("main")

        if root is None:
            raise ValueError("Main content not found")

        if page_type == "program":
            return cls.map_program(
                root, url, slug, observed_at
            )

        return cls.map_event(
            root, url, slug, observed_at
        )
