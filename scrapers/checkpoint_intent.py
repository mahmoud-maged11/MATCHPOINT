from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from scrapers.incremental_window import (
    IncrementalWindow,
    require_utc,
    format_utc,
    parse_modified_gmt,
)


@dataclass(frozen=True, slots=True)
class CheckpointIntent:

    run_id: UUID
    source_name: str
    collection_scope: str
    previous_run_id: UUID | None
    previous_watermark: datetime
    window: IncrementalWindow

    def __post_init__(self):

        if not isinstance(self.run_id, UUID):
            raise TypeError("Invalid run ID")

        if (
            self.previous_run_id is not None
            and not isinstance(self.previous_run_id, UUID)
        ):
            raise TypeError("Invalid previous run ID")

        if self.previous_run_id == self.run_id:
            raise ValueError("Self-referencing checkpoint")

        if self.source_name != "egyincs":
            raise ValueError("Unsupported incremental source")

        if self.collection_scope not in {"jobs", "lp_course"}:
            raise ValueError("Unsupported incremental scope")

        if not isinstance(self.window, IncrementalWindow):
            raise TypeError("Invalid incremental window")

        previous = require_utc(self.previous_watermark)

        if previous.microsecond:
            raise ValueError("Second precision required")

        if not self.window.lower < previous < self.window.upper:
            raise ValueError("Invalid watermark progression")

        object.__setattr__(
            self,
            "previous_watermark",
            previous,
        )

    @property
    def target_watermark(self):

        return self.window.upper

    def to_metadata(self):

        return {
            "version": 1,
            "run_id": str(self.run_id),
            "source_name": self.source_name,
            "collection_scope": self.collection_scope,
            "previous_run_id": (
                str(self.previous_run_id)
                if self.previous_run_id is not None
                else None
            ),
            "previous_watermark": format_utc(
                self.previous_watermark
            ),
            "window_lower": format_utc(self.window.lower),
            "window_upper": format_utc(self.window.upper),
        }

    @classmethod
    def from_metadata(cls, metadata):

        if not isinstance(metadata, dict):
            raise TypeError("Expected intent dictionary")

        required = {
            "version",
            "run_id",
            "source_name",
            "collection_scope",
            "previous_run_id",
            "previous_watermark",
            "window_lower",
            "window_upper",
        }

        if set(metadata) != required:
            raise ValueError("Invalid intent fields")

        if (
            type(metadata["version"]) is not int
            or metadata["version"] != 1
        ):
            raise ValueError("Unsupported intent version")

        previous_run_id = metadata["previous_run_id"]

        intent = cls(
            run_id=UUID(metadata["run_id"]),
            source_name=metadata["source_name"],
            collection_scope=metadata["collection_scope"],
            previous_run_id=(
                UUID(previous_run_id)
                if previous_run_id is not None
                else None
            ),
            previous_watermark=parse_modified_gmt(
                metadata["previous_watermark"]
            ),
            window=IncrementalWindow(
                lower=parse_modified_gmt(
                    metadata["window_lower"]
                ),
                upper=parse_modified_gmt(
                    metadata["window_upper"]
                ),
            ),
        )

        if intent.to_metadata() != metadata:
            raise ValueError("Noncanonical intent metadata")

        return intent

    def validate_binding(
        self,
        *,
        run_id,
        source_name,
        collection_scope,
    ):

        if (
            self.run_id != run_id
            or self.source_name != source_name
            or self.collection_scope != collection_scope
        ):
            raise ValueError("Checkpoint intent binding mismatch")
