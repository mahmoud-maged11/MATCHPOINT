from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from scrapers.models import Opportunity
from scrapers.source_config import get_source_config
from scrapers.utils.invalid_records import InvalidRecord


class CollectionStatus(StrEnum):

    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    ABORTED = "aborted"


class StopReason(StrEnum):

    SOURCE_EXHAUSTED = "source_exhausted"
    REQUESTED_LIMIT = "requested_limit"
    INPUT_EXHAUSTED = "input_exhausted"
    SOURCE_ERROR = "source_error"
    PARSING_ERROR = "parsing_error"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


SUCCESS_REASONS = frozenset({
    StopReason.SOURCE_EXHAUSTED,
    StopReason.REQUESTED_LIMIT,
    StopReason.INPUT_EXHAUSTED,
})


@dataclass(frozen=True, slots=True)
class CollectionResult:

    run_id: UUID
    source_name: str

    opportunities: tuple[Opportunity, ...] = ()
    invalid_records: tuple[InvalidRecord, ...] = ()

    status: CollectionStatus = CollectionStatus.PARTIAL
    stop_reason: StopReason = StopReason.UNKNOWN

    def __post_init__(self):

        if not isinstance(self.run_id, UUID):
            raise TypeError("run_id must be a UUID")

        config = get_source_config(self.source_name)

        if not config.enabled:
            raise ValueError("Source is disabled")

        if not isinstance(self.status, CollectionStatus):
            raise TypeError("Invalid collection status")

        if not isinstance(self.stop_reason, StopReason):
            raise TypeError("Invalid stop reason")

        object.__setattr__(
            self,
            "opportunities",
            tuple(self.opportunities),
        )

        object.__setattr__(
            self,
            "invalid_records",
            tuple(self.invalid_records),
        )

        if self.status == CollectionStatus.COMPLETED:

            if self.stop_reason not in SUCCESS_REASONS:

                raise ValueError(
                    "Completed collection requires "
                    "a confirmed successful stop reason"
                )

        elif self.stop_reason in SUCCESS_REASONS:

            raise ValueError(
                "Successful stop reason requires "
                "completed collection status"
            )

        if self.status == CollectionStatus.ABORTED:

            if self.stop_reason != StopReason.INTERRUPTED:

                raise ValueError(
                    "Aborted collection requires "
                    "interrupted stop reason"
                )

        elif self.stop_reason == StopReason.INTERRUPTED:

            raise ValueError(
                "Interrupted collection must be aborted"
            )

        if (
            self.status == CollectionStatus.FAILED
            and self.opportunities
        ):

            raise ValueError(
                "Failed collection with accepted "
                "opportunities must be partial"
            )

        for opportunity in self.opportunities:

            if not isinstance(opportunity, Opportunity):
                raise TypeError("Invalid opportunity type")

            if opportunity.source_name != self.source_name:

                raise ValueError(
                    "Opportunity source mismatch"
                )

        for record in self.invalid_records:

            if not isinstance(record, InvalidRecord):
                raise TypeError("Invalid rejection type")

            if record.source_name != self.source_name:

                raise ValueError(
                    "Invalid record source mismatch"
                )

            if UUID(record.run_id) != self.run_id:

                raise ValueError(
                    "Invalid record run ID mismatch"
                )

    @property
    def accepted_count(self) -> int:

        return len(self.opportunities)

    @property
    def rejected_count(self) -> int:

        return len(self.invalid_records)

    @property
    def returned_count(self) -> int:

        return self.accepted_count + self.rejected_count

    @property
    def scope_completed(self) -> bool:

        return self.status == CollectionStatus.COMPLETED

    @property
    def source_exhausted(self) -> bool:

        return (
            self.scope_completed
            and self.stop_reason == StopReason.SOURCE_EXHAUSTED
        )
