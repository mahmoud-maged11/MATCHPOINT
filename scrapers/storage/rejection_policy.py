
import hashlib
import hmac
import json
import re

from dataclasses import dataclass

from scrapers.utils.invalid_records import InvalidRecord


SAFE_ERROR_CODES = frozenset({
    "ValueError",
    "TypeError",
    "KeyError",
    "AttributeError",
    "ValidationError",
    "MissingRequiredField",
    "SourceIdentityError",
})


@dataclass(frozen=True, slots=True)
class SanitizedRejection:

    failure_stage: str
    error_code: str
    error_message: str
    source_opportunity_id: str | None
    source_url: str | None
    record_payload: dict


def positive_id(value):

    if type(value) is int:

        if 0 < value <= 9223372036854775807:
            return str(value)

        return None

    if isinstance(value, str):

        if re.fullmatch(r"[1-9][0-9]{0,18}", value):
            return value

    return None


def safe_token(value):

    if not isinstance(value, str):
        return None

    if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        return value

    return None


def allowed_value(value, allowed):

    if isinstance(value, str) and value in allowed:
        return value

    return None


class RejectionPolicy:

    def __init__(self, fingerprint_key: bytes):

        if not isinstance(fingerprint_key, bytes):
            raise TypeError(
                "Fingerprint key must be bytes"
            )

        if len(fingerprint_key) < 32:
            raise ValueError(
                "Fingerprint key must contain at least 32 bytes"
            )

        self._fingerprint_key = fingerprint_key

    def fingerprint(self, record: InvalidRecord) -> str:

        serialized = json.dumps(
            {
                "source_name": record.source_name,
                "source_url": record.source_url,
                "raw_payload": record.raw_payload,
                "error_type": record.error_type,
            },
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        )

        return hmac.new(
            self._fingerprint_key,
            (
                "matchpoint:rejection-evidence:v1|"
                + serialized
            ).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def sanitize(
        self,
        record: InvalidRecord,
    ) -> SanitizedRejection:

        if not isinstance(record, InvalidRecord):

            raise TypeError(
                "Expected an InvalidRecord"
            )

        source = record.source_name
        raw = record.raw_payload

        payload = {
            "policy_version": 1,
            "evidence_fingerprint": self.fingerprint(
                record
            ),
        }

        identifier = None

        def keep(key, value):

            if value is not None:
                payload[key] = value

            return value

        if source == "wuzzuf":

            identifier = keep(
                "api_id",
                safe_token(raw.get("api_id")),
            )

        elif source == "forasna":

            identifier = keep(
                "source_id",
                positive_id(raw.get("source_id")),
            )

        elif source == "egyincs":

            identifier = keep(
                "id",
                positive_id(raw.get("id")),
            )

            keep(
                "endpoint",
                allowed_value(
                    raw.get("endpoint"),
                    {"jobs", "lp_course"},
                ),
            )

        elif source == "itida":

            page_type = keep(
                "page_type",
                allowed_value(
                    raw.get("page_type"),
                    {"program", "event"},
                ),
            )

            slug = keep(
                "slug",
                safe_token(raw.get("slug")),
            )

            if page_type and slug:

                identifier = (
                    f"{page_type}:{slug.lower()}"
                )

        elif source == "nti":

            initiative = keep(
                "initiative",
                allowed_value(
                    raw.get("initiative"),
                    {
                        "hire_ready",
                        "upskilling",
                        "creativa",
                    },
                ),
            )

            track_id = keep(
                "track_id",
                positive_id(raw.get("track_id")),
            )

            center_id = keep(
                "center_id",
                positive_id(raw.get("center_id")),
            )

            if initiative and track_id:

                if initiative == "creativa":

                    if center_id:

                        identifier = (
                            f"{initiative}:{track_id}"
                            f":center:{center_id}"
                        )

                elif raw.get("center_id") is None:

                    identifier = (
                        f"{initiative}:{track_id}"
                    )

        elif source == "bayt":

            identifier = keep(
                "job_id",
                positive_id(raw.get("job_id")),
            )

        elif source == "devpost":

            identifier = keep(
                "id",
                positive_id(raw.get("id")),
            )

            keep(
                "open_state",
                allowed_value(
                    raw.get("open_state"),
                    {"open", "upcoming", "closed"},
                ),
            )

        elif source == "un_volunteers":

            identifier = keep(
                "assignment_id",
                positive_id(raw.get("assignment_id")),
            )

        else:

            raise ValueError(
                "Unsupported rejection source"
            )

        error_code = (
            record.error_type
            if record.error_type in SAFE_ERROR_CODES
            else "ScraperRecordError"
        )

        if error_code == "MissingRequiredField":

            stage = "extraction"

        elif error_code == "ValidationError":

            stage = "validation"

        elif error_code == "SourceIdentityError":

            stage = "identity"

        else:

            stage = "mapping"

        return SanitizedRejection(
            failure_stage=stage,
            error_code=error_code,
            error_message=(
                "Source record rejected during collection"
            ),
            source_opportunity_id=identifier,
            source_url=None,
            record_payload=payload,
        )
