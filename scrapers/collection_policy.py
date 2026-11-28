from dataclasses import dataclass
from enum import StrEnum

from scrapers.collection_result import (
    CollectionResult,
    StopReason,
)


class LoadStrategy(StrEnum):
    BOUNDED = "bounded"
    FULL = "full"
    INCREMENTAL = "incremental"


class CoverageStatus(StrEnum):
    EXHAUSTED = "exhausted"
    LIMITED = "limited"
    INPUT_ONLY = "input_only"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class CollectionPolicy:

    strategy: LoadStrategy = LoadStrategy.BOUNDED
    max_jobs: int | None = 20
    max_pages: int | None = 10
    page_size: int = 20

    def __post_init__(self):

        if not isinstance(self.strategy, LoadStrategy):
            raise TypeError("Invalid load strategy")

        for name in ("max_jobs", "max_pages", "page_size"):

            value = getattr(self, name)

            if value is None and name != "page_size":
                continue

            if type(value) is not int or value <= 0:
                raise ValueError(
                    f"{name} must be a positive integer"
                )

        if self.strategy == LoadStrategy.BOUNDED:

            if self.max_jobs is None or self.max_pages is None:
                raise ValueError(
                    "Bounded collection requires explicit limits"
                )

    def remaining_jobs(self, accepted: int) -> int | None:

        if type(accepted) is not int or accepted < 0:
            raise ValueError("Invalid accepted count")

        if self.max_jobs is None:
            return None

        return max(0, self.max_jobs - accepted)

    def jobs_limit_reached(self, accepted: int) -> bool:

        return self.remaining_jobs(accepted) == 0

    def pages_limit_reached(self, fetched: int) -> bool:

        if type(fetched) is not int or fetched < 0:
            raise ValueError("Invalid page count")

        return (
            self.max_pages is not None
            and fetched >= self.max_pages
        )

    def next_page_size(self, accepted: int) -> int:

        remaining = self.remaining_jobs(accepted)

        if remaining is None:
            return self.page_size

        return min(self.page_size, remaining)


def classify_coverage(
    result: CollectionResult,
) -> CoverageStatus:

    if not isinstance(result, CollectionResult):
        raise TypeError("Expected CollectionResult")

    if not result.scope_completed:
        return CoverageStatus.INCOMPLETE

    if result.stop_reason == StopReason.SOURCE_EXHAUSTED:
        return CoverageStatus.EXHAUSTED

    if result.stop_reason == StopReason.REQUESTED_LIMIT:
        return CoverageStatus.LIMITED

    if result.stop_reason == StopReason.INPUT_EXHAUSTED:
        return CoverageStatus.INPUT_ONLY

    return CoverageStatus.INCOMPLETE


def checkpoint_coverage_eligible(
    result: CollectionResult,
    *,
    strategy: LoadStrategy,
    source_boundary_verified: bool,
) -> bool:

    if not isinstance(strategy, LoadStrategy):
        raise TypeError("Invalid load strategy")

    if type(source_boundary_verified) is not bool:
        raise TypeError("Expected boolean boundary evidence")

    coverage = classify_coverage(result)

    return (
        strategy in {
            LoadStrategy.FULL,
            LoadStrategy.INCREMENTAL,
        }
        and coverage == CoverageStatus.EXHAUSTED
        and result.rejected_count == 0
        and source_boundary_verified
    )
