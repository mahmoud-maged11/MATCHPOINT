import hashlib
import json

from decimal import Decimal

from scrapers.models import Opportunity


HASH_VERSION = 1

UNORDERED_FIELDS = (
    "required_skills",
    "categories",
    "employment_types",
    "work_modes",
)

DECIMAL_FIELDS = (
    "salary_min",
    "salary_max",
    "experience_years_min",
    "experience_years_max",
)


def _normalize_fields(
    payload: dict,
    opportunity: Opportunity,
) -> dict:

    for field in UNORDERED_FIELDS:

        if payload[field] is not None:
            payload[field] = sorted(payload[field])

    for field in DECIMAL_FIELDS:

        value = getattr(opportunity, field)

        if value is not None:

            number = Decimal(value)
            normalized = format(number, "f")

            if "." in normalized:
                normalized = normalized.rstrip("0").rstrip(".")

            payload[field] = (
                "0" if number == 0 else normalized
            )

    return payload


def _serialize_and_hash(
    payload: dict,
) -> str:

    serialized = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def generate_content_hash(
    opportunity: Opportunity,
) -> str:

    content = opportunity.model_dump(
        mode="json",
        exclude={
            "source_name",
            "source_opportunity_id",
            "source_url",
            "collected_at",
            "raw_payload",
        },
    )

    content = _normalize_fields(
        content,
        opportunity,
    )

    for field in ("published_at", "deadline"):

        if content[f"{field}_precision"] == "relative":

            content.pop(field, None)
            content.pop(f"{field}_raw", None)

    return _serialize_and_hash(content)


def generate_observation_hash(
    opportunity: Opportunity,
) -> str:

    observation = opportunity.model_dump(
        mode="json",
    )

    observation = _normalize_fields(
        observation,
        opportunity,
    )

    payload = {
        "hash_version": HASH_VERSION,
        "hash_type": "observation",
        "opportunity": observation,
    }

    return _serialize_and_hash(payload)