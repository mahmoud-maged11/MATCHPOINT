from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from scrapers.source_config import get_source_config
from scrapers.storage.postgres import PostgresStorage

from scrapers.storage.checkpoints import (
    CheckpointAdvance,
    CheckpointRepository,
)
from scrapers.utils.hashing import HASH_VERSION


CONTRACT_VERSION = "3.0.0"

COLLECTION_MODES = frozenset({
    "api",
    "html",
    "live",
})

FINAL_STATUSES = frozenset({
    "completed",
    "partial",
    "failed",
    "aborted",
})


class CollectionRunError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RunCounters:

    received: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    invalid: int = 0
    stale: int = 0
    conflicted: int = 0

    def __post_init__(self) -> None:

        values = {
            "received": self.received,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "invalid": self.invalid,
            "stale": self.stale,
            "conflicted": self.conflicted,
        }

        for name, value in values.items():

            if type(value) is not int or value < 0:
                raise ValueError(
                    f"{name} must be a non-negative integer"
                )

        if self.processed > self.received:
            raise ValueError(
                "Processed records exceed received records"
            )

    @property
    def processed(self) -> int:

        return (
            self.inserted
            + self.updated
            + self.unchanged
            + self.invalid
            + self.stale
            + self.conflicted
        )

    @property
    def unprocessed(self) -> int:

        return self.received - self.processed


class CollectionRunManager:

    def __init__(self, storage: PostgresStorage) -> None:
        self.storage = storage

    def start_run(
        self,
        *,
        source_name: str,
        collection_mode: str,
        collection_scope: str = "default",
        metadata: dict | None = None,
        run_id: UUID | None = None,
    ) -> UUID:

        source_config = get_source_config(source_name)

        if not source_config.enabled:
            raise ValueError(
                f"Source is disabled: {source_name}"
            )

        if collection_mode not in COLLECTION_MODES:
            raise ValueError(
                f"Invalid collection mode: {collection_mode}"
            )

        if not collection_scope.strip():
            raise ValueError(
                "Collection scope cannot be empty"
            )

        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError(
                "Run metadata must be a dictionary"
            )

        if run_id is not None and not isinstance(run_id, UUID):
            raise ValueError("run_id must be a UUID")

        run_id = run_id if run_id is not None else uuid4()

        started_at = datetime.now(timezone.utc)

        with self.storage.transaction() as conn:

            conn.execute(
                """
                INSERT INTO bronze.collection_runs (
                    run_id,
                    source_name,
                    collection_scope,
                    collection_mode,
                    status,
                    started_at,
                    contract_version,
                    hash_version,
                    metadata
                )
                VALUES (
                    %s, %s, %s, %s,
                    'running',
                    %s, %s, %s, %s
                )
                """,
                (
                    run_id,
                    source_name,
                    collection_scope,
                    collection_mode,
                    started_at,
                    CONTRACT_VERSION,
                    HASH_VERSION,
                    Jsonb(metadata if metadata is not None else {}),
                ),
            )

        return run_id

    def get_run(self, run_id: UUID) -> dict | None:

        with self.storage.transaction(read_only=True) as conn:

            return conn.execute(
                """
                SELECT *
                FROM bronze.collection_runs
                WHERE run_id = %s
                """,
                (run_id,),
            ).fetchone()


    def seal_checkpoint_coverage(
        self,
        *,
        intent,
        result,
        evidence,
    ):

        from scrapers.checkpoint_intent import CheckpointIntent
        from scrapers.checkpoint_coverage import (
            validate_coverage_evidence,
        )

        if not isinstance(intent, CheckpointIntent):
            raise TypeError("Expected CheckpointIntent")

        if not validate_coverage_evidence(
            intent=intent,
            result=result,
            metadata=evidence,
        ):
            raise ValueError("Verified coverage is required")

        with self.storage.transaction() as conn:

            row = conn.execute(
                """
                SELECT *
                FROM bronze.collection_runs
                WHERE run_id = %s
                FOR UPDATE
                """,
                (intent.run_id,),
            ).fetchone()

            if row is None:
                raise RuntimeError("Collection run not found")

            intent.validate_binding(
                run_id=row["run_id"],
                source_name=row["source_name"],
                collection_scope=row["collection_scope"],
            )

            if row["status"] != "running":
                raise RuntimeError("Collection run is not running")

            metadata = row["metadata"]

            if metadata.get("checkpoint_intent") != intent.to_metadata():
                raise RuntimeError("Persisted checkpoint intent mismatch")

            if "checkpoint_coverage" in metadata:

                existing = metadata["checkpoint_coverage"]

                if existing != evidence:
                    raise RuntimeError("Checkpoint coverage conflict")

                return row

            updated = conn.execute(
                """
                UPDATE bronze.collection_runs
                SET metadata = jsonb_set(
                    metadata,
                    '{checkpoint_coverage}',
                    %s,
                    TRUE
                )
                WHERE run_id = %s
                RETURNING *
                """,
                (Jsonb(evidence), intent.run_id),
            ).fetchone()

            if updated is None:
                raise RuntimeError("Coverage persistence failed")

            return updated

    def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        counters: RunCounters | None = None,
        received: int | None = None,
        error_message: str | None = None,
        checkpoint: CheckpointAdvance | None = None,
        skip_unsafe_checkpoint: bool = False,
        skip_checkpoint_conflict: bool = False,
    ) -> dict:

        if type(skip_checkpoint_conflict) is not bool:
            raise TypeError(
                "skip_checkpoint_conflict must be a boolean"
            )

        if type(skip_unsafe_checkpoint) is not bool:
            raise TypeError(
                "skip_unsafe_checkpoint must be a boolean"
            )

        if checkpoint is not None:

            if not isinstance(
                checkpoint,
                CheckpointAdvance,
            ):
                raise TypeError(
                    "checkpoint must be a CheckpointAdvance"
                )

            if status != "completed":
                raise ValueError(
                    "Only completed runs can advance checkpoints"
                )

        if status not in FINAL_STATUSES:
            raise ValueError(
                f"Invalid final status: {status}"
            )

        if counters is not None and not isinstance(
            counters, RunCounters
        ):
            raise TypeError(
                "counters must be a RunCounters instance"
            )

        if counters is not None and received is not None:
            raise ValueError(
                "Provide either counters or received, not both"
            )

        if counters is None and received is None:
            raise ValueError(
                "A received record count is required"
            )

        if counters is not None:
            received = counters.received

        if type(received) is not int or received < 0:
            raise ValueError(
                "received must be a non-negative integer"
            )

        if status == "completed" and error_message is not None:
            raise ValueError(
                "Completed runs cannot contain a run-level error"
            )

        if status in {"failed", "aborted", "partial"}:

            if not error_message or not error_message.strip():
                raise ValueError(
                    f"An error message is required for {status} runs"
                )

        with self.storage.transaction() as conn:

            existing = conn.execute(
                """
                SELECT status
                FROM bronze.collection_runs
                WHERE run_id = %s
                FOR UPDATE
                """,
                (run_id,),
            ).fetchone()

            if existing is None:
                raise CollectionRunError(
                    f"Collection run not found: {run_id}"
                )

            if existing["status"] != "running":
                raise CollectionRunError(
                    f"Collection run already finalized: {run_id}"
                )

            from scrapers.storage.counters import (
                RunCounterRepository,
            )

            actual_counters = RunCounterRepository.calculate(
                conn,
                run_id=run_id,
                received=received,
            )

            if counters is not None and counters != actual_counters:
                raise CollectionRunError(
                    "Provided counters do not match persisted outcomes"
                )

            counters = actual_counters

            requested_checkpoint = checkpoint

            if (
                checkpoint is not None
                and skip_unsafe_checkpoint
                and (
                    counters.invalid > 0
                    or counters.stale > 0
                    or counters.conflicted > 0
                )
            ):
                checkpoint = None

            if status == "completed" and counters.unprocessed != 0:
                raise ValueError(
                    "Completed runs cannot contain unprocessed records"
                )

            result = conn.execute(
                """
                UPDATE bronze.collection_runs
                SET
                    status = %s,
                    finished_at = GREATEST(
                        clock_timestamp(),
                        started_at
                    ),
                    records_received = %s,
                    records_inserted = %s,
                    records_updated = %s,
                    records_unchanged = %s,
                    records_invalid = %s,
                    records_stale = %s,
                    records_conflicted = %s,
                    error_message = %s
                WHERE run_id = %s
                  AND status = 'running'
                RETURNING *
                """,
                (
                    status,
                    counters.received,
                    counters.inserted,
                    counters.updated,
                    counters.unchanged,
                    counters.invalid,
                    counters.stale,
                    counters.conflicted,
                    error_message,
                    run_id,
                ),
            ).fetchone()

            if result is None:
                raise CollectionRunError(
                    f"Collection run finalization failed: {run_id}"
                )

            checkpoint_outcome = "skipped_unsafe_counters"

            if checkpoint is not None:

                from scrapers.storage.checkpoints import (
                    ConcurrentCheckpointError,
                )

                try:

                    with conn.transaction():

                        CheckpointRepository._advance(
                            conn,
                            run_id=run_id,
                            advance=checkpoint,
                        )

                    checkpoint_outcome = "advanced"

                except ConcurrentCheckpointError:

                    if not skip_checkpoint_conflict:
                        raise

                    checkpoint_outcome = (
                        "skipped_checkpoint_conflict"
                    )

            if requested_checkpoint is not None:

                receipt = {
                    "version": 1,
                    "outcome": checkpoint_outcome,
                    "checkpoint_type": (
                        requested_checkpoint.checkpoint_type
                    ),
                    "checkpoint_value": (
                        requested_checkpoint.checkpoint_value
                    ),
                    "expected_previous_run_id": (
                        str(
                            requested_checkpoint.expected_previous_run_id
                        )
                        if requested_checkpoint.expected_previous_run_id
                        is not None
                        else None
                    ),
                }

                result = conn.execute(
                    '''
                    UPDATE bronze.collection_runs
                    SET metadata = jsonb_set(
                        metadata,
                        '{checkpoint_finalization}',
                        %s,
                        TRUE
                    )
                    WHERE run_id = %s
                    RETURNING *
                    ''',
                    (Jsonb(receipt), run_id),
                ).fetchone()

                if result is None:
                    raise CollectionRunError(
                        "Checkpoint receipt persistence failed"
                    )

            return result