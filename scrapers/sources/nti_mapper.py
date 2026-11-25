
import re

from bs4 import BeautifulSoup

from scrapers.models import Opportunity


class NTIMapper:

    BASE_URL = "https://www.nti.sci.eg"

    INITIATIVES = {
        "hire_ready": "HireReady",
        "upskilling": "Upskilling Programs",
        "creativa": "CREATIVA",
    }

    EMPTY_VALUES = {
        "na", "n/a", "none", "nil", "not applicable"
    }

    @staticmethod
    def clean_text(value):

        if not isinstance(value, str):
            return ""

        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def clean_soup(cls, html):

        soup = BeautifulSoup(html, "lxml")

        for node in soup.select("script, style, noscript"):
            if not node.decomposed:
                node.decompose()

        return soup

    @classmethod
    def extract_sections(cls, html):

        soup = cls.clean_soup(html)

        sections = []
        part = None

        for heading in soup.select("h2, h3"):

            title = cls.clean_text(
                heading.get_text(" ", strip=True)
            )

            if heading.name == "h2":
                part = title
                continue

            items = []

            for sibling in heading.next_siblings:

                if getattr(sibling, "name", None) in {
                    "h1", "h2", "h3"
                }:
                    break

                if getattr(sibling, "name", None) in {
                    "ul", "ol"
                }:

                    for item in sibling.find_all(
                        "li", recursive=False
                    ):
                        text = cls.clean_text(
                            item.get_text(" ", strip=True)
                        )

                        if text:
                            items.append(text)

                elif getattr(sibling, "name", None) == "p":

                    text = cls.clean_text(
                        sibling.get_text(" ", strip=True)
                    )

                    if text:
                        items.append(text)

            sections.append({
                "part": part,
                "heading": title,
                "items": items,
            })

        return sections


    @classmethod
    def extract_duration(cls, html):

        soup = cls.clean_soup(html)

        durations = {
            "total_hours": None,
            "technical_hours": None,
            "career_hours": None,
            "business_hours": None,
            "freelance_hours": None,
        }

        business_part = False

        for heading in soup.select("h1, h2, h3"):

            text = cls.clean_text(
                heading.get_text(" ", strip=True)
            )

            lower = text.lower()

            if lower.startswith("module name:"):
                business_part = "business skills" in lower

            match = re.search(
                r"(\d+)\s*hours?\b",
                text,
                re.IGNORECASE
            )

            if not match:
                continue

            hours = int(match.group(1))

            if hours <= 0:
                continue

            if heading.name == "h1":
                durations["total_hours"] = hours

            elif lower.startswith("module name:"):

                if business_part:
                    durations["business_hours"] = hours
                else:
                    durations["total_hours"] = hours

            elif re.match(
                r"^(?:part\s*1\s*[:\-]?\s*)?technical\b",
                lower
            ):
                durations["technical_hours"] = hours

            elif re.match(
                r"^(?:part\s*2\s*[:\-]?\s*)?"
                r"career development\b",
                lower
            ):
                durations["career_hours"] = hours

            elif (
                heading.name == "h2"
                and "freelance" in lower
            ):
                durations["freelance_hours"] = hours

            elif business_part and lower.startswith("duration"):
                durations["business_hours"] = hours

        return durations


    @classmethod
    def extract_prerequisites(cls, sections):

        required = []
        optional = []
        notes = []
        explicit_none = False

        for section in sections:

            heading = section["heading"].lower().rstrip(":")

            if not re.fullmatch(
                r"(?:module\s+)?prerequisites?",
                heading
            ):
                continue

            for item in section["items"]:

                normalized = item.lower().strip(" .")

                if normalized in cls.EMPTY_VALUES:
                    explicit_none = True
                    continue

                if re.match(
                    r"^(?:there (?:are|is) )?no "
                    r"(?:formal )?prerequisites?\b",
                    normalized
                ):
                    explicit_none = True
                    notes.append(item)
                    continue

                if re.fullmatch(
                    r"(?:learners|students|participants|"
                    r"trainees|candidates) are expected "
                    r"to have the following skills:?",
                    normalized
                ):
                    notes.append(item)
                    continue

                if re.search(
                    r"\bnot optional\b"
                    r"|\bnot recommended\b",
                    normalized
                ):
                    if "not optional" in normalized:
                        required.append(item)
                    else:
                        notes.append(item)

                elif re.search(
                    r"\b(optional|desirable|preferred|"
                    r"recommended|advantageous)\b"
                    r"|\bnot required\b"
                    r"|\bnot mandatory\b",
                    normalized
                ):
                    optional.append(item)

                else:
                    required.append(item)

        return {
            "required": list(dict.fromkeys(required)),
            "optional": list(dict.fromkeys(optional)),
            "notes": list(dict.fromkeys(notes)),
            "explicit_none": explicit_none,
        }


    @classmethod
    def extract_audience(cls, sections):

        audience = []

        for section in sections:

            heading = section["heading"].lower().rstrip(":")

            if heading == "target audience":
                audience.append({
                    "part": section["part"],
                    "items": section["items"],
                })

        return audience

    @classmethod
    def map_course(cls, listing, html, career_html=None):

        initiative = listing["initiative"]
        track_id = str(listing["track_id"])
        center_id = listing.get("center_id")

        if initiative not in cls.INITIATIVES:
            raise ValueError("Unsupported NTI initiative")

        if not re.fullmatch(r"[1-9]\d*", track_id):
            raise ValueError("Invalid NTI track ID")

        title = cls.clean_text(listing.get("title"))

        if not title:
            raise ValueError("Missing NTI course title")

        soup = cls.clean_soup(html)

        detail_title = soup.find("h1")

        if detail_title is None:
            raise ValueError("Missing NTI detail heading")

        sections = cls.extract_sections(html)

        if not any(section["items"] for section in sections):
            raise ValueError("Missing NTI course details")

        durations = cls.extract_duration(html)

        if career_html:

            career_durations = cls.extract_duration(career_html)

            durations["career_hours"] = (
                career_durations["career_hours"]
            )

        if durations["total_hours"] is None:

            technical = durations["technical_hours"]

            additional = [
                durations["career_hours"],
                durations["business_hours"],
                durations["freelance_hours"],
            ]

            known = [
                value for value in additional
                if value is not None
            ]

            if technical is not None and known:
                durations["total_hours"] = technical + sum(known)

        prerequisites = cls.extract_prerequisites(sections)
        audience = cls.extract_audience(sections)

        description_parts = []

        for section in sections:

            heading = section["heading"].lower().rstrip(":")

            if heading in {
                "overview",
                "scope",
                "module description",
            }:

                # Avoid duplicating the shared secondary program.
                if section["part"] and re.search(
                    r"part\s*2\b",
                    section["part"],
                    re.IGNORECASE
                ):
                    continue

                description_parts.extend(section["items"])

        requirement_parts = []

        for entry in audience:

            label = entry["part"] or "Target audience"

            requirement_parts.append(
                label + ": " + "; ".join(entry["items"])
            )

        if prerequisites["required"]:

            requirement_parts.append(
                "Prerequisites: "
                + "; ".join(prerequisites["required"])
            )

        if prerequisites["optional"]:

            requirement_parts.append(
                "Optional prerequisites: "
                + "; ".join(prerequisites["optional"])
            )

        if prerequisites["notes"]:

            requirement_parts.append(
                "Prerequisite notes: "
                + "; ".join(prerequisites["notes"])
            )

        if (
            prerequisites["explicit_none"]
            and not prerequisites["required"]
            and not prerequisites["optional"]
        ):

            requirement_parts.append(
                "No prerequisites stated by the source."
            )

        source_id = f"{initiative}:{track_id}"

        if center_id is not None:
            source_id += f":center:{center_id}"

        closed = listing.get("closed") is True

        status = "closed" if closed else "unknown"

        categories = [cls.INITIATIVES[initiative]]

        if listing.get("category"):
            categories.append(listing["category"])

        return Opportunity(
            source_name="nti",
            source_opportunity_id=source_id,
            source_url=listing["source_url"],
            title=title,
            organization="NTI",
            opportunity_type="training",
            description=(
                "\n\n".join(dict.fromkeys(description_parts))
                or None
            ),
            requirements="\n".join(requirement_parts) or None,
            required_skills=(
                prerequisites["required"]
                or (
                    []
                    if prerequisites["explicit_none"]
                    else None
                )
            ),
            categories=categories,
            location=listing.get("location"),
            status=status,
            source_status_raw=listing.get("status_raw"),
            raw_payload={
                "initiative": initiative,
                "track_id": track_id,
                "center_id": center_id,
                "category": listing.get("category"),
                "location": listing.get("location"),
                "detail_url": (
                    cls.BASE_URL
                    + f"/dey/pages/modules/{track_id}.html"
                ),
                "detail_title": cls.clean_text(
                    detail_title.get_text(" ", strip=True)
                ),
                "durations": durations,
                "prerequisites": prerequisites,
                "target_audience": audience,
                "status_raw": listing.get("status_raw"),
            },
        )
