from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

from scrapers.models import Opportunity
from scrapers.utils.dates import normalize_source_datetime


BASE_URL = "https://app.unv.org"


class UNVExcludedOpportunity(ValueError):
    pass


def clean_text(value):

    if not isinstance(value, str):
        return None

    text = BeautifulSoup(
        value, "html.parser"
    ).get_text(" ", strip=True)

    return " ".join(text.split()) or None


def label(value):

    if isinstance(value, dict):
        return clean_text(value.get("label"))

    return clean_text(value)


def code(value):

    if not isinstance(value, dict):
        return None

    nested = value.get("value")

    if isinstance(nested, dict):
        return nested.get("code")

    return value.get("code")


def lookup(value):

    if not isinstance(value, dict):
        return None

    return {
        "label": label(value),
        "code": code(value)
    }


def validate_id(value):

    if type(value) is not int or value <= 0:
        raise ValueError("Invalid UNV assignment ID")

    return value


def is_target_assignment(record):

    onsite = record.get("isOnsite")

    if onsite is False:
        return True

    if onsite is True:
        return code(record.get("country")) == "EGY"

    return False


def extract_languages(record):

    result = []

    for item in record.get("languages") or []:

        if not isinstance(item, dict):
            continue

        language = label(item.get("language"))
        level = label(item.get("level"))

        if not language:
            continue

        entry = {
            "language": language,
            "level": level,
            "required": item.get("isRequired")
        }

        if entry not in result:
            result.append(entry)

    return result


def extract_categories(record):

    result = []

    for item in record.get("expertiseAreas") or []:

        name = label(item)

        if name and name not in result:
            result.append(name)

    return result


def extract_requirements(record, languages):

    sections = []

    skills = clean_text(
        record.get("requiredSkillExperience")
    )

    eligibility = clean_text(
        record.get("additionalEligibilityCriteria")
    )

    education = label(
        record.get("requiredEducation")
    )

    if skills:
        sections.append(skills)

    if eligibility:
        sections.append(
            f"Eligibility: {eligibility}"
        )

    if education:
        sections.append(
            f"Education: {education}"
        )

    for item in languages:

        text = item["language"]

        if item["level"]:
            text += f" - {item['level']}"

        if item["required"] is True:
            text += " (Required)"

        sections.append(text)

    return "\n".join(sections) or None


def extract_category_details(record):

    category = record.get(
        "volunteersCategoryDetails"
    )

    if not isinstance(category, dict):
        return {}

    fields = (
        "volunteersCategory",
        "categoryName",
        "categoryType",
        "workArrangement",
        "assignmentDuration",
        "workLocation"
    )

    return {
        field: lookup(category.get(field))
        for field in fields
    }


def extract_employment_types(category):

    arrangement = code(
        category.get("workArrangement")
    )

    mapping = {
        "FULLTIME": "full_time",
        "PARTTIME": "part_time"
    }

    if arrangement in mapping:
        return [mapping[arrangement]]

    return []


def extract_dates(listing, detail):

    published_raw = (
        listing.get("publishDate")
        or detail.get("publishDate")
    )

    published_at, published_precision = (
        normalize_source_datetime(published_raw)
    )

    deadline_raw = detail.get("sourcingEndDate")

    # The API and UI display different closing times.
    # Preserve the original value without inventing
    # an exact UTC timestamp.

    deadline = None
    deadline_precision = (
        "unknown" if deadline_raw else None
    )

    return {
        "published_at": published_at,
        "published_at_raw": published_raw,
        "published_at_precision": published_precision,
        "deadline": deadline,
        "deadline_raw": deadline_raw,
        "deadline_precision": deadline_precision
    }


def resolve_status(detail, observed_at):

    status_code = code(detail.get("status"))

    if status_code != "DOA_SOURCING":
        raise UNVExcludedOpportunity(
            "Assignment is not recruiting"
        )

    if detail.get("isSourcingActive") is not True:
        raise UNVExcludedOpportunity(
            "Assignment sourcing is not active"
        )

    if detail.get("isReserved") is not False:
        raise UNVExcludedOpportunity(
            "Reserved or unverified assignment"
        )

    if detail.get("isSingleSource") is not False:
        raise UNVExcludedOpportunity(
            "Single-source or unverified recruitment"
        )

    deadline_raw = detail.get("sourcingEndDate")

    if not isinstance(deadline_raw, str):
        return "unknown"

    try:

        deadline_date = datetime.fromisoformat(
            deadline_raw.replace("Z", "+00:00")
        ).date()

    except ValueError:
        return "unknown"

    # Conservative expiration check because the
    # exact closing timezone is not established.

    if (
        observed_at.date()
        > deadline_date + timedelta(days=2)
    ):
        raise UNVExcludedOpportunity(
            "Assignment deadline has passed"
        )

    if observed_at.date() >= deadline_date:
        return "unknown"

    return "active"


def map_un_volunteers_opportunity(
    listing,
    detail,
    observed_at=None
):

    observed_at = (
        observed_at
        or datetime.now(timezone.utc)
    )

    if observed_at.utcoffset() is None:
        raise ValueError(
            "Observation timestamp must be timezone-aware"
        )

    observed_at = observed_at.astimezone(
        timezone.utc
    )

    record_id = validate_id(listing.get("id"))

    if validate_id(detail.get("id")) != record_id:
        raise ValueError("Assignment ID mismatch")

    if listing.get("isOnsite") is not detail.get("isOnsite"):
        raise ValueError("Assignment modality mismatch")

    if not is_target_assignment(detail):
        raise UNVExcludedOpportunity(
            "Assignment outside target scope"
        )

    status = resolve_status(
        detail, observed_at
    )

    title = clean_text(detail.get("name"))

    if not title:
        raise ValueError("Missing assignment title")

    description = clean_text(
        detail.get("taskDescription")
    )

    if not description:
        raise ValueError("Missing task description")

    host = detail.get("hostEntity") or {}

    organization = clean_text(
        host.get("name")
    )

    onsite = detail["isOnsite"]

    country = label(detail.get("country"))

    category = extract_category_details(detail)

    languages = extract_languages(detail)

    categories = extract_categories(detail)

    requirements = extract_requirements(
        detail, languages
    )

    dates = extract_dates(listing, detail)

    # Explicit whitelist. Never persist the complete
    # API response or recruitment contact information.

    raw_payload = {
        "assignment_id": record_id,
        "assignment_reference": detail.get(
            "doaRequestNo"
        ),
        "country": lookup(detail.get("country")),
        "is_onsite": onsite,
        "status": lookup(detail.get("status")),
        "is_sourcing_active": detail.get(
            "isSourcingActive"
        ),
        "is_reserved": detail.get("isReserved"),
        "is_single_source": detail.get(
            "isSingleSource"
        ),
        "can_apply": detail.get("canApply"),
        "duration_raw": detail.get("duration"),
        "hours_per_week": lookup(
            detail.get("hoursWeek")
        ),
        "required_experience_raw": detail.get(
            "requiredExperience"
        ),
        "experience_unit_raw": detail.get(
            "unitOfExperience"
        ),
        "education": lookup(
            detail.get("requiredEducation")
        ),
        "languages": languages,
        "volunteer_category": category,
        "volunteer_category_code": detail.get(
            "volunteersCategoryCode"
        ),
        "nationality_category": detail.get(
            "national"
        ),
        "volunteers_number": detail.get(
            "volunteersNumber"
        ),
        "sdg": lookup(detail.get("sdgType")),
        "task_type": lookup(detail.get("taskType")),
        "context": clean_text(detail.get("context")),
        "additional_eligibility": clean_text(
            detail.get("additionalEligibilityCriteria")
        ),
        "start_date_raw": detail.get("startDate"),
        "expected_end_date_raw": detail.get(
            "expectedEndDate"
        ),
        "detail_publish_date_raw": detail.get(
            "publishDate"
        ),
        "possibility_of_extension": detail.get(
            "possibilityOfExtension"
        ),
        "egypt_eligibility": "unverified",
        "compensation_type": (
            "unpaid" if not onsite else "unverified"
        )
    }

    return Opportunity(
        source_name="un_volunteers",
        source_opportunity_id=str(record_id),
        source_url=f"{BASE_URL}/opportunities/{record_id}",
        title=title,
        organization=organization,
        description=description,
        opportunity_type="volunteering",
        location=country,
        work_modes=[
            "on_site" if onsite else "remote"
        ],
        employment_types=extract_employment_types(
            category
        ),
        categories=categories,
        education_level=label(
            detail.get("requiredEducation")
        ),
        requirements=requirements,
        collected_at=observed_at,
        status=status,
        source_status_raw=label(
            detail.get("status")
        ),
        raw_payload=raw_payload,
        **dates
    )