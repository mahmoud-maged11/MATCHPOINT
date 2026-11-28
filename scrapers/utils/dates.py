import re

from datetime import datetime, timezone, timedelta


def is_date_only(value: str | None) -> bool:

    if not isinstance(value, str):
        return False

    return bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip())
        or re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", value.strip())
    )


def parse_source_datetime(value: str | None) -> datetime | None:

    if not isinstance(value, str) or not value.strip():
        return None

    value = value.strip()

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        pass

    for date_format in (
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y"
    ):

        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue

    return None


def normalize_source_datetime(value):

    parsed = parse_source_datetime(value)

    if parsed is None:
        return None, "unknown"

    if is_date_only(value):
        return None, "date_only"

    if parsed.utcoffset() is None:
        return None, "unknown"

    try:
        return parsed.astimezone(timezone.utc), "exact"
    except (ValueError, OverflowError):
        return None, "unknown"


def resolve_opportunity_status(
    source_status: str | None,
    deadline_raw: str | None,
    observed_at: datetime
) -> str:

    if observed_at.utcoffset() is None:
        raise ValueError(
            "Observation time must be timezone-aware"
        )

    if source_status in ("closed", "expired"):
        return source_status

    if source_status != "active":
        return "unknown"

    deadline = parse_source_datetime(deadline_raw)

    if deadline is None:
        return "active"

    observed_at = observed_at.astimezone(timezone.utc)

    if is_date_only(deadline_raw):

        deadline += timedelta(days=1)

    if deadline.utcoffset() is not None:

        return (
            "expired"
            if deadline <= observed_at
            else "active"
        )

    latest_possible_deadline = (
        deadline.replace(tzinfo=timezone.utc)
        + timedelta(hours=12)
    )

    return (
        "expired"
        if latest_possible_deadline <= observed_at
        else "active"
    )