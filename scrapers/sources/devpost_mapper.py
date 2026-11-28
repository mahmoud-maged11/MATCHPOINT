import json
import re

from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin

from bs4 import BeautifulSoup

from scrapers.models import Opportunity
from scrapers.utils.dates import (
    normalize_source_datetime,
    resolve_opportunity_status,
)


class DevpostExcludedOpportunity(ValueError):
    pass


class DevpostEligibilityUnverified(DevpostExcludedOpportunity):
    pass


def clean_text(value):

    if not isinstance(value, str):
        return None

    return " ".join(value.split()) or None


def validate_source_url(url):

    if not isinstance(url, str):
        raise ValueError("Missing Devpost URL")

    parsed = urlsplit(url)

    if (
        parsed.scheme != "https"
        or not re.fullmatch(
            r"[a-z0-9-]+\.devpost\.com",
            parsed.netloc
        )
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid Devpost opportunity URL")

    return f"https://{parsed.netloc}/"


def validate_source_id(value):

    if type(value) is not int or value <= 0:
        raise ValueError("Invalid Devpost source ID")

    return str(value)


def extract_text(soup, selector):

    element = soup.select_one(selector)

    if element is None:
        return None

    return clean_text(
        element.get_text(" ", strip=True)
    )


def iter_json_objects(value):

    if isinstance(value, dict):

        yield value

        for child in value.values():
            yield from iter_json_objects(child)

    elif isinstance(value, list):

        for child in value:
            yield from iter_json_objects(child)


def extract_event(soup):

    events = []

    for script in soup.select(
        'script[type="application/ld+json"]'
    ):

        try:
            payload = json.loads(script.get_text())
        except (ValueError, TypeError):
            continue

        for item in iter_json_objects(payload):

            types = item.get("@type", [])

            if isinstance(types, str):
                types = [types]

            if isinstance(types, list) and any(
                isinstance(value, str)
                and value.endswith("Event")
                for value in types
            ):
                events.append(item)

    if len(events) == 1:
        return events[0]

    return {}


def extract_categories(record):

    themes = record.get("themes")

    if not isinstance(themes, list):
        return None

    categories = []
    seen = set()

    for theme in themes:

        if not isinstance(theme, dict):
            continue

        name = clean_text(theme.get("name"))

        if name and name.casefold() not in seen:

            categories.append(name)
            seen.add(name.casefold())

    return categories or None


def extract_organization(record, event):

    organization = clean_text(
        record.get("organization_name")
    )

    if organization:
        return organization

    organizer = event.get("organizer")

    if isinstance(organizer, dict):
        return clean_text(organizer.get("name"))

    return None


def extract_eligibility(soup):

    eligibility = extract_text(
        soup,
        "#eligibility-list"
    )

    country_list = soup.select_one(
        "#eligibility-countries-modal-list"
    )

    country_title = extract_text(
        soup,
        "#eligibility-countries-modal-title"
    )

    egypt_names = {
        "egypt",
        "arab republic of egypt",
        "egypt arab republic of",
        "egypt, arab republic of",
    }

    def country_key(value):

        normalized = value.casefold()

        if normalized in egypt_names:
            return "egypt"

        return normalized

    def restriction_kind(value):

        text = (value or "").casefold()

        included = (
            "only specific countries" in text
            or "countries included" in text
            or "territories included" in text
        )

        excluded = (
            "specific countries/territories excluded" in text
            or "countries excluded" in text
            or "territories excluded" in text
        )

        if included and excluded:

            raise DevpostEligibilityUnverified(
                "Conflicting country restrictions"
            )

        if included:
            return "allow"

        if excluded:
            return "block"

        return None

    eligibility_kind = restriction_kind(eligibility)

    modal_kind = restriction_kind(country_title)

    if (
        modal_kind is None
        and country_title
        and "excluded" in country_title.casefold()
    ):
        modal_kind = "block"

    if (
        eligibility_kind
        and modal_kind
        and eligibility_kind != modal_kind
    ):

        raise DevpostEligibilityUnverified(
            "Conflicting country restrictions"
        )

    kind = eligibility_kind or modal_kind

    modal_countries = []

    if country_list:

        modal_countries = [
            text
            for item in country_list.select("li")
            if (text := clean_text(
                item.get_text(" ", strip=True)
            ))
        ]

    tooltip_lists = []

    for tooltip in soup.select(
        "#eligibility-list li span[data-tooltip]"
    ):

        label = clean_text(
            tooltip.get_text(" ", strip=True)
        )

        label_kind = restriction_kind(label)

        if label_kind is None:
            continue

        if kind and kind != label_kind:

            raise DevpostEligibilityUnverified(
                "Conflicting country restrictions"
            )

        kind = label_kind

        raw = clean_text(tooltip.get("title"))

        if not raw:

            raise DevpostEligibilityUnverified(
                "Country tooltip unavailable"
            )

        parts = [
            clean_text(part)
            for part in raw.split(",")
        ]

        if not parts or any(
            not part for part in parts
        ):

            raise DevpostEligibilityUnverified(
                "Invalid country tooltip"
            )

        # Preserve the known comma-containing Egypt alias.
        countries = []

        index = 0

        while index < len(parts):

            current = parts[index]

            if (
                current.casefold() == "egypt"
                and index + 1 < len(parts)
                and parts[index + 1].casefold()
                    == "arab republic of"
            ):

                countries.append(
                    "Egypt, Arab Republic of"
                )

                index += 2

            else:

                countries.append(current)
                index += 1

        tooltip_lists.append(countries)

    candidates = []

    if modal_countries:
        candidates.append(modal_countries)

    candidates.extend(tooltip_lists)

    if candidates:

        reference = {
            country_key(value)
            for value in candidates[0]
        }

        for candidate in candidates[1:]:

            if {
                country_key(value)
                for value in candidate
            } != reference:

                raise DevpostEligibilityUnverified(
                    "Conflicting country lists"
                )

        countries = candidates[0]

    else:

        countries = []

    if country_title is None and tooltip_lists:

        country_title = (
            "Countries included"
            if kind == "allow"
            else "Countries excluded"
        )

    included_countries = (
        countries if kind == "allow" else []
    )

    excluded_countries = (
        countries if kind == "block" else []
    )

    if kind == "allow":

        if not included_countries:

            raise DevpostEligibilityUnverified(
                "Country allowlist unavailable"
            )

        if not any(
            country_key(country) == "egypt"
            for country in included_countries
        ):

            raise DevpostExcludedOpportunity(
                "Egypt not present in country allowlist"
            )

    if kind == "block":

        if not excluded_countries:

            raise DevpostEligibilityUnverified(
                "Country blocklist unavailable"
            )

        if any(
            country_key(country) == "egypt"
            for country in excluded_countries
        ):

            raise DevpostExcludedOpportunity(
                "Egypt is explicitly excluded"
            )

    return {
        "eligibility": eligibility,
        "included_countries": included_countries,
        "country_list_title": country_title,
        "listed_countries": countries,
        "excluded_countries": excluded_countries,
        "egypt_eligibility": "unverified",
    }


def extract_action_links(soup, source_url):

    registration_url = None
    rules_url = None

    source_host = urlsplit(source_url).netloc

    for element in soup.select("a[href]"):

        text = clean_text(
            element.get_text(" ", strip=True)
        )

        if not text:
            continue

        url = urljoin(source_url, element["href"])
        parsed = urlsplit(url)

        if (
            parsed.scheme != "https"
            or parsed.netloc != source_host
        ):
            continue

        if (
            text.casefold() in (
                "join hackathon",
                "register"
            )
            and parsed.path == "/register"
        ):
            registration_url = registration_url or url

        if (
            text.casefold() in (
                "rules",
                "view full rules"
            )
            and parsed.path == "/rules"
        ):
            rules_url = rules_url or url

    return registration_url, rules_url


def extract_requirements(soup):

    requirements = extract_text(
        soup,
        "#challenge-requirements"
    )

    if requirements:
        return requirements

    description = soup.select_one(
        "#challenge-description"
    )

    if description is None:
        return None

    for heading in description.select(
        "h2, h3, h4, h5"
    ):

        text = clean_text(
            heading.get_text(" ", strip=True)
        )

        if text and text.casefold() == "requirements":

            parts = []

            for sibling in heading.next_siblings:

                if getattr(sibling, "name", None) in (
                    "h2", "h3", "h4"
                ):
                    break

                if hasattr(sibling, "get_text"):

                    value = clean_text(
                        sibling.get_text(" ", strip=True)
                    )

                else:
                    value = clean_text(str(sibling))

                if value:
                    parts.append(value)

            return " ".join(parts) or None

    return None


def extract_deadline(record, event):

    raw = clean_text(event.get("endDate"))

    if raw:
        return raw

    period = clean_text(
        record.get("submission_period_dates")
    )

    if not period:
        return None

    match = re.search(
        r"([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})$",
        period
    )

    if not match:
        return None

    try:

        return datetime.strptime(
            match.group(0),
            "%b %d, %Y"
        ).date().isoformat()

    except ValueError:
        return None


def extract_prize(record):

    value = record.get("prize_amount")

    if not isinstance(value, str):
        return None

    return clean_text(
        BeautifulSoup(
            value,
            "html.parser"
        ).get_text("", strip=True)
    )


def map_devpost_opportunity(
    record: dict,
    detail_html: str,
    observed_at: datetime | None = None
) -> Opportunity:

    if not isinstance(record, dict):
        raise ValueError("Invalid Devpost record")

    observed_at = (
        observed_at
        or datetime.now(timezone.utc)
    )

    if observed_at.utcoffset() is None:
        raise ValueError(
            "Observation time must be timezone-aware"
        )

    source_id = validate_source_id(
        record.get("id")
    )

    source_url = validate_source_url(
        record.get("url")
    )

    title = clean_text(record.get("title"))

    if not title:
        raise ValueError("Missing hackathon title")

    if record.get("invite_only") is not False:
        raise DevpostExcludedOpportunity(
            "Private or unverified invitation status"
        )

    displayed_location = record.get(
        "displayed_location"
    )

    if not isinstance(displayed_location, dict):
        raise ValueError("Missing location information")

    location = clean_text(
        displayed_location.get("location")
    )

    if not location or location.casefold() != "online":
        raise DevpostExcludedOpportunity(
            "Hackathon is not explicitly online"
        )

    source_status = clean_text(
        record.get("open_state")
    )

    if source_status not in ("open", "upcoming"):
        raise DevpostExcludedOpportunity(
            "Hackathon is not open or upcoming"
        )

    soup = BeautifulSoup(
        detail_html,
        "html.parser"
    )

    canonical = soup.select_one(
        'link[rel="canonical"][href]'
    )

    if canonical:

        canonical_url = validate_source_url(
            canonical["href"]
        )

        if canonical_url != source_url:
            raise ValueError(
                "Canonical URL does not match API URL"
            )

    event = extract_event(soup)

    description = extract_text(
        soup,
        "#challenge-description"
    )

    if not description:

        raw_description = event.get("description")

        if isinstance(raw_description, str):

            description = clean_text(
                BeautifulSoup(
                    raw_description,
                    "html.parser"
                ).get_text(" ", strip=True)
            )

    if not description:
        raise ValueError(
            "Missing hackathon description"
        )

    eligibility = extract_eligibility(soup)

    requirements = extract_requirements(soup)

    eligibility_text = eligibility["eligibility"]

    if eligibility_text:

        requirements = "\n\n".join(
            part for part in (
                requirements,
                f"Eligibility: {eligibility_text}"
            )
            if part
        )

    registration_url, rules_url = (
        extract_action_links(soup, source_url)
    )

    deadline_raw = extract_deadline(
        record,
        event
    )

    deadline, deadline_precision = (
        normalize_source_datetime(deadline_raw)
        if deadline_raw
        else (None, None)
    )

    normalized_status = (
        "active"
        if source_status == "open"
        else "unknown"
    )

    status = resolve_opportunity_status(
        source_status=normalized_status,
        deadline_raw=deadline_raw,
        observed_at=observed_at
    )

    if status == "expired":
        raise DevpostExcludedOpportunity(
            "Submission deadline has passed"
        )

    raw_payload = {
        "api_id": source_id,
        "open_state": source_status,
        "displayed_location": displayed_location,
        "submission_period_dates": record.get(
            "submission_period_dates"
        ),
        "time_left_to_submission": record.get(
            "time_left_to_submission"
        ),
        "submission_start_raw": event.get(
            "startDate"
        ),
        "submission_end_raw": event.get(
            "endDate"
        ),
        "deadline_kind": "submission",
        "registration_deadline": None,
        "registration_url": registration_url,
        "rules_url": rules_url,
        "prize_amount_raw": extract_prize(record),
        "prizes_counts": record.get(
            "prizes_counts"
        ),
        "registrations_count": record.get(
            "registrations_count"
        ),
        "invite_only": record.get(
            "invite_only"
        ),
        "themes": record.get("themes"),
        **eligibility,
    }

    return Opportunity(
        source_name="devpost",
        source_opportunity_id=source_id,
        source_url=source_url,
        title=title,
        organization=extract_organization(
            record,
            event
        ),
        description=description,
        opportunity_type="hackathon",
        location="Online",
        work_modes=["remote"],
        categories=extract_categories(record),
        requirements=requirements,
        deadline=deadline,
        deadline_raw=deadline_raw,
        deadline_precision=deadline_precision,
        collected_at=observed_at,
        status=status,
        source_status_raw=source_status,
        raw_payload=raw_payload,
    )