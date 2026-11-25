import hashlib
import json

from decimal import Decimal

from scrapers.models import Opportunity


def generate_content_hash(
    opportunity: Opportunity
) -> str:

    content = opportunity.model_dump(
        mode="json",
        exclude={
            "source_name",
            "source_opportunity_id",
            "source_url",
            "collected_at",
            "raw_payload"
        }
    )

    unordered_fields = (
        "required_skills",
        "categories",
        "employment_types",
        "work_modes"
    )

    for field in unordered_fields:

        if content[field] is not None:
            content[field] = sorted(content[field])

    decimal_fields = (
        "salary_min",
        "salary_max",
        "experience_years_min",
        "experience_years_max"
    )

    for field in decimal_fields:

        value = getattr(opportunity, field)

        if value is not None:

            number = Decimal(value)
            normalized = format(number, "f")

            if "." in normalized:
                normalized = normalized.rstrip("0").rstrip(".")

            content[field] = (
                "0" if number == 0 else normalized
            )

    for field in ("published_at", "deadline"):

        if content[f"{field}_precision"] == "relative":

            content.pop(field, None)
            content.pop(f"{field}_raw", None)

    serialized_content = json.dumps(
        content,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":")
    )

    return hashlib.sha256(
        serialized_content.encode("utf-8")
    ).hexdigest()