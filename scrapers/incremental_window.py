import re

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


DEFAULT_OVERLAP = timedelta(minutes=5)
DEFAULT_SAFETY_LAG = timedelta(minutes=2)

GMT_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:Z|[+]00:00)?"
)


def require_utc(value):

    if not isinstance(value, datetime):
        raise TypeError("Expected datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime required")

    return value.astimezone(timezone.utc)


def parse_modified_gmt(value):

    if not isinstance(value, str):
        raise ValueError("Missing modification timestamp")

    if GMT_PATTERN.fullmatch(value) is None:
        raise ValueError("Invalid modification timestamp")

    parsed = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return require_utc(parsed)


def format_utc(value):

    return require_utc(value).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


@dataclass(frozen=True, slots=True)
class IncrementalWindow:

    lower: datetime
    upper: datetime

    def __post_init__(self):

        lower = require_utc(self.lower)
        upper = require_utc(self.upper)

        if lower.microsecond or upper.microsecond:
            raise ValueError("Second precision required")

        if lower >= upper:
            raise ValueError("Invalid incremental window")

        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint,
        *,
        now,
        overlap=DEFAULT_OVERLAP,
        safety_lag=DEFAULT_SAFETY_LAG,
    ):

        checkpoint = require_utc(checkpoint)
        now = require_utc(now)

        for value in (overlap, safety_lag):

            if not isinstance(value, timedelta):
                raise TypeError("Expected timedelta")

            if value < timedelta(0):
                raise ValueError("Negative duration")

        if overlap < timedelta(seconds=1):
            raise ValueError("Overlap must be at least one second")

        if checkpoint > now:
            raise ValueError("Checkpoint is in the future")

        upper = (now - safety_lag).replace(
            microsecond=0
        )

        if upper <= checkpoint:
            raise ValueError("No safe forward window")

        lower = (checkpoint - overlap).replace(
            microsecond=0
        )

        return cls(lower=lower, upper=upper)

    def api_params(self):

        return {
            "modified_after": format_utc(self.lower),
            "modified_before": format_utc(self.upper),
            "orderby": "modified",
            "order": "desc",
        }

    def contains(self, timestamp):

        timestamp = require_utc(timestamp)

        return self.lower <= timestamp <= self.upper


@dataclass(slots=True)
class PaginationEvidence:

    window: IncrementalWindow
    page_size: int
    ordering: str = "modified_desc"
    last_source_id: int | None = field(
        default=None, init=False,
    )

    pages_seen: int = field(default=0, init=False)
    expected_total: int | None = field(default=None, init=False)
    expected_pages: int | None = field(default=None, init=False)

    seen_ids: set[int] = field(
        default_factory=set,
        init=False,
    )

    last_modified: datetime | None = field(
        default=None,
        init=False,
    )

    exhausted: bool = field(default=False, init=False)
    failed: bool = field(default=False, init=False)

    def __post_init__(self):

        if self.ordering not in {
            "modified_desc", "id_asc",
        }:
            raise ValueError(
                "Unsupported pagination ordering"
            )

        if not isinstance(self.window, IncrementalWindow):
            raise TypeError("Expected IncrementalWindow")

        if type(self.page_size) is not int or self.page_size <= 0:
            raise ValueError("Invalid page size")

    def observe(
        self,
        *,
        page,
        records,
        total,
        total_pages,
    ):

        if self.failed:
            raise ValueError("Pagination already invalid")

        try:

            self._observe(
                page=page,
                records=records,
                total=total,
                total_pages=total_pages,
            )

        except (ValueError, TypeError):

            self.failed = True
            self.exhausted = False
            raise

    def _observe(
        self,
        *,
        page,
        records,
        total,
        total_pages,
    ):

        if self.exhausted:
            raise ValueError("Pagination already exhausted")

        if type(page) is not int or page != self.pages_seen + 1:
            raise ValueError("Non-sequential page")

        if type(total) is not int or total < 0:
            raise ValueError("Invalid total")

        if type(total_pages) is not int or total_pages < 0:
            raise ValueError("Invalid total pages")

        calculated_pages = (
            total + self.page_size - 1
        ) // self.page_size

        if total_pages != calculated_pages:
            raise ValueError("Inconsistent pagination metadata")

        if not isinstance(records, list):
            raise ValueError("Invalid records container")

        if self.expected_total is not None:

            if total != self.expected_total:
                raise ValueError("Record total changed")

            if total_pages != self.expected_pages:
                raise ValueError("Page total changed")

        if total == 0:

            if page != 1 or records:
                raise ValueError("Invalid empty response")

            self.expected_total = 0
            self.expected_pages = 0
            self.pages_seen = 1
            self.exhausted = True

            return

        if page > total_pages:
            raise ValueError("Page exceeds declared total")

        expected_count = min(
            self.page_size,
            total - ((page - 1) * self.page_size),
        )

        if len(records) != expected_count:
            raise ValueError("Unexpected page record count")

        page_ids = set()
        last_modified = self.last_modified
        last_source_id = self.last_source_id

        for record in records:

            if not isinstance(record, dict):
                raise ValueError("Invalid record")

            source_id = record.get("id")

            if type(source_id) is not int or source_id <= 0:
                raise ValueError("Invalid source ID")

            if source_id in self.seen_ids or source_id in page_ids:
                raise ValueError("Repeated source ID")

            modified = parse_modified_gmt(
                record.get("modified_gmt")
            )

            if not self.window.contains(modified):
                raise ValueError("Record outside requested window")

            if self.ordering == "modified_desc":

                if (
                    last_modified is not None
                    and modified > last_modified
                ):
                    raise ValueError(
                        "Modification order changed"
                    )

            elif (
                last_source_id is not None
                and source_id <= last_source_id
            ):
                raise ValueError(
                    "Source ID order changed"
                )

            last_source_id = source_id

            page_ids.add(source_id)
            last_modified = modified

        self.expected_total = total
        self.expected_pages = total_pages

        self.seen_ids.update(page_ids)
        self.last_modified = last_modified
        self.last_source_id = last_source_id
        self.pages_seen += 1

        if page == total_pages:

            if len(self.seen_ids) != total:
                raise ValueError("Incomplete record coverage")

            self.exhausted = True

    @property
    def boundary_verified(self):

        return (
            not self.failed
            and self.exhausted
            and self.expected_total is not None
            and len(self.seen_ids) == self.expected_total
        )
