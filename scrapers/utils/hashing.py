import hashlib
import json

from scrapers.models import Opportunity


def generate_content_hash(opportunity: Opportunity) -> str:

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