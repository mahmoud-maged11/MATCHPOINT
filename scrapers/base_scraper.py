
from abc import ABC, abstractmethod
from uuid import UUID, uuid4

from scrapers.collection_result import (
    CollectionResult,
    CollectionStatus,
    StopReason,
    SUCCESS_REASONS,
)
from scrapers.models import Opportunity
from scrapers.source_config import get_source_config
from scrapers.utils.invalid_records import InvalidRecord
from scrapers.utils.http_client import HTTPClient
from scrapers.utils.logger import get_logger


class BaseScraper(ABC):

    def __init__(self, source_name: str):

        self.source_name = source_name
        self.source_config = get_source_config(source_name)
        self.logger = get_logger(source_name)
        self.client = HTTPClient(self.source_config)

        self.run_id: str | None = None
        self.invalid_records: list[InvalidRecord] = []

        self._running = False
        self._stop_reason = StopReason.UNKNOWN
        self._collection_issue: StopReason | None = None

        self.last_result: CollectionResult | None = None

    @abstractmethod
    def scrape(self) -> list[Opportunity]:

        pass

    def record_invalid(
        self,
        raw_payload: dict,
        error_type: str,
        error_message: str,
        source_url: str | None = None,
    ) -> None:

        if self.run_id is None:

            raise RuntimeError(
                "Collection run has not been initialized"
            )

        record = InvalidRecord(
            run_id=self.run_id,
            source_name=self.source_name,
            source_url=source_url,
            raw_payload=raw_payload,
            error_type=error_type,
            error_message=error_message,
        )

        self.invalid_records.append(record)

        self.logger.warning(
            f"Invalid record | "
            f"Run ID: {self.run_id} | "
            f"Error: {error_type}"
        )

    def mark_collection_complete(
        self,
        reason: StopReason,
    ) -> None:

        if not self._running:

            raise RuntimeError(
                "No active collection run"
            )

        if (
            not isinstance(reason, StopReason)
            or reason not in SUCCESS_REASONS
        ):

            raise ValueError(
                "Invalid successful stop reason"
            )

        self._stop_reason = reason

    def mark_collection_issue(
        self,
        reason: StopReason,
    ) -> None:

        if not self._running:

            raise RuntimeError(
                "No active collection run"
            )

        if (
            not isinstance(reason, StopReason)
            or reason not in {
                StopReason.SOURCE_ERROR,
                StopReason.PARSING_ERROR,
            }
        ):

            raise ValueError(
                "Invalid collection issue reason"
            )

        if self._collection_issue is None:

            self._collection_issue = reason

        self.logger.warning(
            f"Collection issue | "
            f"Run ID: {self.run_id} | "
            f"Reason: {reason.value}"
        )

    @staticmethod
    def _resolve_run_id(
        run_id: UUID | str | None,
    ) -> str:

        if run_id is None:

            return str(uuid4())

        if isinstance(run_id, UUID):

            return str(run_id)

        if isinstance(run_id, str):

            try:

                return str(UUID(run_id))

            except ValueError as error:

                raise ValueError(
                    "run_id must be a valid UUID"
                ) from error

        raise TypeError(
            "run_id must be a UUID, string or None"
        )

    def _build_result(
        self,
        opportunities: list[Opportunity],
        *,
        status: CollectionStatus | None = None,
        stop_reason: StopReason | None = None,
    ) -> CollectionResult:

        if self.run_id is None:

            raise RuntimeError(
                "Collection run has not been initialized"
            )

        if status is None:

            if self._collection_issue is not None:

                stop_reason = self._collection_issue

                status = (
                    CollectionStatus.PARTIAL
                    if opportunities or self.invalid_records
                    else CollectionStatus.FAILED
                )

            elif self._stop_reason in SUCCESS_REASONS:

                status = CollectionStatus.COMPLETED
                stop_reason = self._stop_reason

            else:

                status = CollectionStatus.PARTIAL
                stop_reason = StopReason.UNKNOWN

        if stop_reason is None:

            raise ValueError(
                "Collection stop reason is required"
            )

        return CollectionResult(
            run_id=UUID(self.run_id),
            source_name=self.source_name,
            opportunities=tuple(opportunities),
            invalid_records=tuple(self.invalid_records),
            status=status,
            stop_reason=stop_reason,
        )

    def run(
        self,
        *,
        run_id: UUID | str | None = None,
    ) -> list[Opportunity]:

        if self._running:

            raise RuntimeError(
                "Scraper is already running"
            )

        resolved_run_id = self._resolve_run_id(run_id)

        self.run_id = resolved_run_id
        self.invalid_records = []
        self.last_result = None

        self._stop_reason = StopReason.UNKNOWN
        self._collection_issue = None
        self._running = True

        opportunities: list[Opportunity] = []
        primary_error: BaseException | None = None

        try:

            self.logger.info(
                f"Scraper started | Run ID: {self.run_id}"
            )

            opportunities = self.scrape()

            self.last_result = self._build_result(
                opportunities
            )

            self.logger.info(
                f"Collected {len(opportunities)} opportunities | "
                f"Run ID: {self.run_id}"
            )

            self.logger.info(
                f"Rejected {len(self.invalid_records)} records | "
                f"Run ID: {self.run_id}"
            )

            return opportunities

        except KeyboardInterrupt as error:

            primary_error = error

            self.last_result = self._build_result(
                opportunities,
                status=CollectionStatus.ABORTED,
                stop_reason=StopReason.INTERRUPTED,
            )

            raise

        except Exception as error:

            primary_error = error

            self.last_result = self._build_result(
                opportunities,
                status=(
                    CollectionStatus.PARTIAL
                    if opportunities or self.invalid_records
                    else CollectionStatus.FAILED
                ),
                stop_reason=(
                    self._collection_issue
                    or StopReason.UNKNOWN
                ),
            )

            self.logger.error(
                f"Scraper failed | "
                f"Run ID: {self.run_id} | "
                f"Error type: {type(error).__name__}"
            )

            raise

        except BaseException as error:

            primary_error = error

            raise

        finally:

            try:

                self.client.close()

            except Exception as error:

                self.logger.error(
                    f"Client close failed | "
                    f"Run ID: {self.run_id} | "
                    f"Error type: {type(error).__name__}"
                )

                if primary_error is None:

                    self.last_result = self._build_result(
                        opportunities,
                        status=(
                            CollectionStatus.PARTIAL
                            if opportunities or self.invalid_records
                            else CollectionStatus.FAILED
                        ),
                        stop_reason=StopReason.UNKNOWN,
                    )

                    raise

            finally:

                self._running = False

                self.logger.info(
                    f"Scraper finished | Run ID: {self.run_id}"
                )

    def run_with_result(
        self,
        *,
        run_id: UUID | str | None = None,
    ) -> CollectionResult:

        self.run(run_id=run_id)

        if self.last_result is None:

            raise RuntimeError(
                "Collection result was not generated"
            )

        return self.last_result
