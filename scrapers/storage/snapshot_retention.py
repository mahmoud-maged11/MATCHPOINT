import stat

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from scrapers.storage.collection_runs import (
    CollectionRunManager,
)

from scrapers.storage.collection_snapshot import (
    CollectionSnapshotStore,
    SnapshotError,
)

from scrapers.storage.postgres import PostgresStorage

from scrapers.storage.recovery_lock import (
    RecoveryLockManager,
    RecoveryAlreadyRunningError,
)


DEFAULT_RETENTION_DAYS = 30


@dataclass(frozen=True, slots=True)
class RetentionDecision:

    run_id: UUID | None
    filename: str
    action: str
    reason: str
    size_bytes: int = 0


@dataclass(frozen=True, slots=True)
class RetentionResult:

    dry_run: bool
    retention_days: int
    cutoff: datetime
    decisions: tuple[RetentionDecision, ...]

    @property
    def scanned(self) -> int:

        return len(self.decisions)

    @property
    def eligible(self) -> int:

        return sum(
            item.action in {"eligible", "deleted"}
            for item in self.decisions
        )

    @property
    def deleted(self) -> int:

        return sum(
            item.action == "deleted"
            for item in self.decisions
        )

    @property
    def retained(self) -> int:

        return sum(
            item.action == "retained"
            for item in self.decisions
        )

    @property
    def skipped(self) -> int:

        return sum(
            item.action == "skipped"
            for item in self.decisions
        )

    @property
    def errors(self) -> int:

        return sum(
            item.action == "error"
            for item in self.decisions
        )

    @property
    def reclaimed_bytes(self) -> int:

        return sum(
            item.size_bytes
            for item in self.decisions
            if item.action == "deleted"
        )

    @property
    def eligible_bytes(self) -> int:

        return sum(
            item.size_bytes
            for item in self.decisions
            if item.action in {"eligible", "deleted"}
        )


class SnapshotRetentionManager:

    def __init__(
        self,
        storage: PostgresStorage,
        snapshot_store: CollectionSnapshotStore,
        *,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ):

        if (
            type(retention_days) is not int
            or retention_days < 1
        ):

            raise ValueError(
                "Retention days must be a positive integer"
            )

        self.storage = storage
        self.snapshot_store = snapshot_store
        self.retention_days = retention_days

        self.runs = CollectionRunManager(storage)

        self.recovery_lock = RecoveryLockManager(
            storage
        )

    @staticmethod
    def _parse_run_id(path: Path) -> UUID | None:

        if path.suffix != ".json":

            return None

        try:

            run_id = UUID(path.stem)

        except ValueError:

            return None

        if path.name != f"{run_id}.json":

            return None

        return run_id

    @staticmethod
    def _validate_now(
        now: datetime | None,
    ) -> datetime:

        if now is None:

            return datetime.now(timezone.utc)

        if not isinstance(now, datetime):

            raise TypeError(
                "now must be a datetime"
            )

        if (
            now.tzinfo is None
            or now.utcoffset() is None
        ):

            raise ValueError(
                "now must be timezone-aware"
            )

        return now.astimezone(timezone.utc)

    def _inspect(
        self,
        path: Path,
        *,
        cutoff: datetime,
        dry_run: bool,
    ) -> RetentionDecision:

        run_id = self._parse_run_id(path)

        def decision(
            action: str,
            reason: str,
            size_bytes: int = 0,
        ) -> RetentionDecision:

            return RetentionDecision(
                run_id=run_id,
                filename=path.name,
                action=action,
                reason=reason,
                size_bytes=size_bytes,
            )

        if run_id is None:

            return decision(
                "skipped",
                "unrecognized_filename",
            )

        try:

            with self.recovery_lock.acquire(
                run_id,
                bind_connection=True,
            ):

                try:

                    initial_stat = path.lstat()

                except FileNotFoundError:

                    return decision(
                        "skipped",
                        "snapshot_disappeared",
                    )

                if not stat.S_ISREG(
                    initial_stat.st_mode
                ):

                    return decision(
                        "skipped",
                        "not_regular_file",
                    )

                if initial_stat.st_nlink != 1:

                    return decision(
                        "retained",
                        "unexpected_hard_links",
                    )

                size = initial_stat.st_size

                run = self.runs.get_run(run_id)

                if run is None:

                    return decision(
                        "retained",
                        "unknown_run",
                        size,
                    )

                if run.get("run_id") != run_id:

                    return decision(
                        "retained",
                        "database_run_mismatch",
                        size,
                    )

                if run["status"] != "completed":

                    return decision(
                        "retained",
                        "run_not_completed",
                        size,
                    )

                counter_names = (
                    "records_received",
                    "records_inserted",
                    "records_updated",
                    "records_unchanged",
                    "records_invalid",
                    "records_stale",
                    "records_conflicted",
                )

                counters = [
                    run.get(name)
                    for name in counter_names
                ]

                if any(
                    type(value) is not int or value < 0
                    for value in counters
                ):

                    return decision(
                        "retained",
                        "invalid_run_counters",
                        size,
                    )

                if counters[0] != sum(counters[1:]):

                    return decision(
                        "retained",
                        "inconsistent_run_counters",
                        size,
                    )

                finished_at = run.get(
                    "finished_at"
                )

                if (
                    not isinstance(
                        finished_at,
                        datetime,
                    )
                    or finished_at.tzinfo is None
                    or finished_at.utcoffset() is None
                ):

                    return decision(
                        "retained",
                        "invalid_finished_at",
                        size,
                    )

                if finished_at > cutoff:

                    return decision(
                        "retained",
                        "within_retention_period",
                        size,
                    )

                try:

                    snapshot = (
                        self.snapshot_store.load(
                            run_id
                        )
                    )

                except SnapshotError:

                    return decision(
                        "retained",
                        "snapshot_verification_failed",
                        size,
                    )

                if (
                    snapshot.run_id != run_id
                    or snapshot.source_name
                    != run["source_name"]
                    or snapshot.status.value
                    != run["status"]
                ):

                    return decision(
                        "retained",
                        "snapshot_run_mismatch",
                        size,
                    )

                current_stat = path.lstat()

                if (
                    not stat.S_ISREG(
                        current_stat.st_mode
                    )
                    or current_stat.st_dev
                    != initial_stat.st_dev
                    or current_stat.st_ino
                    != initial_stat.st_ino
                    or current_stat.st_size
                    != initial_stat.st_size
                    or current_stat.st_mtime_ns
                    != initial_stat.st_mtime_ns
                    or current_stat.st_ctime_ns
                    != initial_stat.st_ctime_ns
                    or current_stat.st_nlink != 1
                ):

                    return decision(
                        "retained",
                        "snapshot_changed",
                        size,
                    )

                if dry_run:

                    return decision(
                        "eligible",
                        "retention_period_expired",
                        size,
                    )

                path.unlink()

                return decision(
                    "deleted",
                    "retention_period_expired",
                    size,
                )

        except RecoveryAlreadyRunningError:

            return decision(
                "skipped",
                "recovery_lock_unavailable",
            )

        except FileNotFoundError:

            return decision(
                "skipped",
                "snapshot_disappeared",
            )

        except Exception as error:

            return decision(
                "error",
                type(error).__name__,
            )

    def cleanup(
        self,
        *,
        dry_run: bool = True,
        now: datetime | None = None,
    ) -> RetentionResult:

        if type(dry_run) is not bool:

            raise TypeError(
                "dry_run must be a boolean"
            )

        if not dry_run and now is not None:

            raise ValueError(
                "Custom evaluation time is allowed "
                "only during dry runs"
            )

        evaluated_at = self._validate_now(now)

        cutoff = evaluated_at - timedelta(
            days=self.retention_days
        )

        directory = self.snapshot_store.directory

        decisions = []

        if directory.exists():

            if not directory.is_dir():

                raise RuntimeError(
                    "Snapshot directory is invalid"
                )

            for path in sorted(
                directory.iterdir()
            ):

                decisions.append(
                    self._inspect(
                        path,
                        cutoff=cutoff,
                        dry_run=dry_run,
                    )
                )

        return RetentionResult(
            dry_run=dry_run,
            retention_days=self.retention_days,
            cutoff=cutoff,
            decisions=tuple(decisions),
        )