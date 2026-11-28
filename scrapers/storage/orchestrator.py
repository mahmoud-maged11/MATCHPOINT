
from dataclasses import dataclass, replace

from scrapers.storage.retry_policy import RetryPolicy
from scrapers.storage.recovery_lock import RecoveryLockManager
from contextlib import contextmanager
from scrapers.storage.collection_snapshot import (
    CollectionSnapshotStore,
)
from scrapers.storage.run_recovery import RunRecovery
from uuid import UUID, uuid4

from scrapers.base_scraper import BaseScraper

from scrapers.storage.identity import (
    SourceIdentity,
    SourceIdentityError,
)

from scrapers.utils.invalid_records import (
    InvalidRecord,
)
from scrapers.collection_result import (
    CollectionResult,
    CollectionStatus,
    StopReason,
)

from scrapers.storage.postgres import PostgresStorage

from scrapers.storage.collection_runs import (
    CollectionRunManager,
)

from scrapers.storage.opportunities import (
    OpportunityRepository,
    IngestionResult,
)

from scrapers.storage.invalid_records import (
    InvalidRecordRepository,
    RejectionResult,
)

from scrapers.storage.rejection_policy import (
    RejectionPolicy,
)

from scrapers.storage.counters import (
    RunCounterRepository,
)

from scrapers.utils.hashing import (
    generate_observation_hash,
)


@dataclass(frozen=True, slots=True)
class AcceptedPersistenceResult:

    received: int
    duplicate_inputs: int
    outcomes: tuple[IngestionResult, ...]

    @property
    def processed(self) -> int:

        return len(self.outcomes)


@dataclass(frozen=True, slots=True)
class RejectedPersistenceResult:

    received: int
    duplicate_inputs: int
    outcomes: tuple[RejectionResult, ...]

    @property
    def processed(self) -> int:

        return len(self.outcomes)

    @property
    def inserted(self) -> int:

        return sum(
            outcome.inserted
            for outcome in self.outcomes
        )

    @property
    def previously_persisted(self) -> int:

        return self.processed - self.inserted


@dataclass(frozen=True, slots=True)
class ExecutionResult:

    run_id: UUID
    collection_status: CollectionStatus
    stop_reason: StopReason
    accepted: AcceptedPersistenceResult
    rejected: RejectedPersistenceResult
    finalized_run: dict

    @property
    def received(self) -> int:

        return (
            self.accepted.received
            + self.rejected.received
        )

    @property
    def duplicate_inputs(self) -> int:

        return (
            self.accepted.duplicate_inputs
            + self.rejected.duplicate_inputs
        )


@dataclass(frozen=True, slots=True)
class RecoveryResult:

    run_id: UUID
    collection_status: CollectionStatus
    stop_reason: StopReason | None
    finalized_run: dict
    collection_result: CollectionResult | None
    already_finalized: bool
    execution: ExecutionResult | None = None

    @property
    def accepted(self):

        if self.execution is None:
            return None

        return self.execution.accepted

    @property
    def rejected(self):

        if self.execution is None:
            return None

        return self.execution.rejected

    @property
    def received(self) -> int:

        return self.finalized_run["records_received"]

    @property
    def duplicate_inputs(self):

        if self.execution is None:
            return None

        return self.execution.duplicate_inputs




class IngestionExecutionError(RuntimeError):

    def __init__(
        self,
        *,
        run_id: UUID,
        stage: str,
        collection_result: CollectionResult | None = None,
    ):

        self.run_id = run_id
        self.stage = stage
        self.collection_result = collection_result

        super().__init__(
            f"Ingestion interrupted at {stage}; "
            f"run_id={run_id}"
        )


class IngestionOrchestrator:

    def __init__(
        self,
        storage: PostgresStorage,
        *,
        rejection_policy: RejectionPolicy | None = None,
        retry_policy: RetryPolicy | None = None,
        snapshot_store: CollectionSnapshotStore | None = None,
        recovery_lock: RecoveryLockManager | None = None,
        batch_size: int = 1,
    ):

        if (
            rejection_policy is not None
            and not isinstance(
                rejection_policy,
                RejectionPolicy,
            )
        ):

            raise TypeError(
                "Expected a RejectionPolicy"
            )

        if (
            snapshot_store is not None
            and not isinstance(
                snapshot_store,
                CollectionSnapshotStore,
            )
        ):
            raise TypeError(
                "Expected a CollectionSnapshotStore"
            )

        if type(batch_size) is not int:

            raise TypeError(
                "Batch size must be an integer"
            )

        if not 1 <= batch_size <= 1000:

            raise ValueError(
                "Batch size must be between 1 and 1000"
            )

        self.batch_size = batch_size

        self.snapshot_store = snapshot_store

        if (
            recovery_lock is not None
            and not isinstance(
                recovery_lock,
                RecoveryLockManager,
            )
        ):
            raise TypeError(
                "Expected a RecoveryLockManager"
            )

        if (
            recovery_lock is not None
            and recovery_lock.storage is not storage
        ):
            raise ValueError(
                "Recovery lock storage mismatch"
            )

        self.recovery_lock = recovery_lock

        self.storage = storage
        self.rejection_policy = rejection_policy

        if (
            retry_policy is not None
            and not isinstance(retry_policy, RetryPolicy)
        ):
            raise TypeError("Expected a RetryPolicy")

        self.retry_policy = (
            retry_policy
            if retry_policy is not None
            else RetryPolicy()
        )

        self.runs = CollectionRunManager(storage)

        self.opportunities = OpportunityRepository(
            storage
        )

        self.invalid_records = InvalidRecordRepository(
            storage
        )

        self.counters = RunCounterRepository(
            storage
        )

    @property
    def run_recovery(self) -> RunRecovery:

        return RunRecovery(
            self.runs,
            self.retry_policy,
        )

    def start_collection(
        self,
        *,
        scraper: BaseScraper,
        collection_mode: str,
        collection_scope: str = "default",
        metadata: dict | None = None,
        run_id: UUID | None = None,
    ) -> UUID:

        if not isinstance(scraper, BaseScraper):

            raise TypeError(
                "Expected a BaseScraper instance"
            )

        return self.run_recovery.start_run(
            source_name=scraper.source_name,
            collection_mode=collection_mode,
            collection_scope=collection_scope,
            metadata=metadata,
            run_id=(
                run_id
                if run_id is not None
                else uuid4()
            ),
        )

    def validate_run(
        self,
        *,
        run_id: UUID,
        source_name: str,
    ) -> dict:

        if not isinstance(run_id, UUID):

            raise TypeError(
                "run_id must be a UUID"
            )

        run = self.retry_policy.execute(
            lambda: self.runs.get_run(run_id)
        )

        if run is None:

            raise ValueError(
                "Collection run does not exist"
            )

        if run["source_name"] != source_name:

            raise ValueError(
                "Collection source does not match run"
            )

        if run["status"] != "running":

            raise ValueError(
                "Collection run is not running"
            )

        return run

    def collect(
        self,
        *,
        scraper: BaseScraper,
        run_id: UUID,
    ) -> CollectionResult:

        if not isinstance(scraper, BaseScraper):

            raise TypeError(
                "Expected a BaseScraper instance"
            )

        self.validate_run(
            run_id=run_id,
            source_name=scraper.source_name,
        )

        result = scraper.run_with_result(
            run_id=run_id
        )

        if not isinstance(result, CollectionResult):

            raise TypeError(
                "Expected a CollectionResult"
            )

        if result.run_id != run_id:

            raise ValueError(
                "Collection result run ID mismatch"
            )

        if result.source_name != scraper.source_name:

            raise ValueError(
                "Collection result source mismatch"
            )

        return result

    def persist_accepted(
        self,
        result: CollectionResult,
    ) -> AcceptedPersistenceResult:

        if not isinstance(result, CollectionResult):

            raise TypeError(
                "Expected a CollectionResult"
            )

        self.validate_run(
            run_id=result.run_id,
            source_name=result.source_name,
        )

        seen = set()
        outcomes = []
        pending = []
        duplicate_inputs = 0

        def flush():

            if not pending:
                return

            batch = tuple(pending)

            if self.batch_size == 1:

                persisted = (
                    self.retry_policy.execute(
                        lambda: self.opportunities.ingest(
                            batch[0],
                            result.run_id,
                        )
                    ),
                )

            else:

                persisted = self.retry_policy.execute(
                    lambda: self.opportunities.ingest_many(
                        batch,
                        result.run_id,
                    )
                )

            if len(persisted) != len(batch):

                raise RuntimeError(
                    "Batch persistence result count mismatch"
                )

            outcomes.extend(persisted)

            pending.clear()

        for opportunity in result.opportunities:

            observation_hash = generate_observation_hash(
                opportunity
            )

            if observation_hash in seen:

                duplicate_inputs += 1
                continue

            seen.add(observation_hash)

            pending.append(opportunity)

            if len(pending) >= self.batch_size:

                flush()

        flush()

        return AcceptedPersistenceResult(
            received=len(seen),
            duplicate_inputs=duplicate_inputs,
            outcomes=tuple(outcomes),
        )


    def persist_rejected(
        self,
        result: CollectionResult,
    ) -> RejectedPersistenceResult:

        if not isinstance(result, CollectionResult):

            raise TypeError(
                "Expected a CollectionResult"
            )

        self.validate_run(
            run_id=result.run_id,
            source_name=result.source_name,
        )

        if not result.invalid_records:

            return RejectedPersistenceResult(
                received=0,
                duplicate_inputs=0,
                outcomes=(),
            )

        if self.rejection_policy is None:

            raise RuntimeError(
                "Rejection policy is required"
            )

        prepared = {}
        duplicate_inputs = 0

        # Sanitize the complete batch before writing.

        for record in result.invalid_records:

            if UUID(record.run_id) != result.run_id:

                raise ValueError(
                    "Invalid record run ID mismatch"
                )

            if record.source_name != result.source_name:

                raise ValueError(
                    "Invalid record source mismatch"
                )

            safe = self.rejection_policy.sanitize(
                record
            )

            rejection_hash = (
                InvalidRecordRepository
                .generate_rejection_hash(
                    source_opportunity_id=(
                        safe.source_opportunity_id
                    ),
                    source_url=safe.source_url,
                    failure_stage=safe.failure_stage,
                    error_code=safe.error_code,
                    record_payload=safe.record_payload,
                )
            )

            if rejection_hash in prepared:

                duplicate_inputs += 1
                continue

            prepared[rejection_hash] = (
                record,
                safe,
            )

        outcomes = []

        for record, safe in prepared.values():

            outcome = self.retry_policy.execute(lambda: self.invalid_records.record(
                run_id=result.run_id,
                source_name=result.source_name,
                failure_stage=safe.failure_stage,
                error_code=safe.error_code,
                error_message=safe.error_message,
                source_opportunity_id=(
                    safe.source_opportunity_id
                ),
                source_url=safe.source_url,
                record_payload=safe.record_payload,
                observed_at=record.collected_at,
            ))

            outcomes.append(outcome)

        return RejectedPersistenceResult(
            received=len(prepared),
            duplicate_inputs=duplicate_inputs,
            outcomes=tuple(outcomes),
        )


    def prepare_collection(
        self,
        result: CollectionResult,
    ) -> CollectionResult:

        if not isinstance(result, CollectionResult):

            raise TypeError(
                "Expected a CollectionResult"
            )

        self.validate_run(
            run_id=result.run_id,
            source_name=result.source_name,
        )

        accepted = []
        rejected = list(result.invalid_records)

        for opportunity in result.opportunities:

            if opportunity.source_name != result.source_name:

                raise ValueError(
                    "Opportunity source mismatch"
                )

            try:

                SourceIdentity.from_opportunity(
                    opportunity
                )

            except SourceIdentityError:

                if self.rejection_policy is None:

                    raise RuntimeError(
                        "Rejection policy is required"
                    )

                rejected.append(
                    InvalidRecord(
                        run_id=str(result.run_id),
                        source_name=result.source_name,
                        source_url=str(
                            opportunity.source_url
                        ),
                        raw_payload={
                            "observation_hash": (
                                generate_observation_hash(
                                    opportunity
                                )
                            ),
                        },
                        error_type="SourceIdentityError",
                        error_message=(
                            "Invalid Bronze source identity"
                        ),
                        collected_at=(
                            opportunity.collected_at
                        ),
                    )
                )

                continue

            accepted.append(opportunity)

        return replace(
            result,
            opportunities=tuple(accepted),
            invalid_records=tuple(rejected),
        )



    def validate_previous_checkpoint(self, intent):

        from datetime import datetime

        from scrapers.storage.checkpoints import (
            CheckpointRepository,
            CheckpointError,
            ConcurrentCheckpointError,
        )

        current = CheckpointRepository(
            self.storage
        ).get_checkpoint(
            source_name=intent.source_name,
            collection_scope=intent.collection_scope,
        )

        if current is None:

            if intent.previous_run_id is not None:

                raise ConcurrentCheckpointError(
                    "Expected checkpoint does not exist"
                )

            return

        if (
            current["last_successful_run_id"]
            != intent.previous_run_id
        ):
            raise ConcurrentCheckpointError(
                "Checkpoint changed before collection"
            )

        if current["checkpoint_type"] != "timestamp":

            raise CheckpointError(
                "Expected timestamp checkpoint"
            )

        previous = datetime.fromisoformat(
            current["checkpoint_value"]["timestamp"]
        )

        if previous != intent.previous_watermark:

            raise CheckpointError(
                "Previous watermark mismatch"
            )

    def resolve_checkpoint_advance(
        self,
        *,
        result,
        prepared,
    ):

        from scrapers.checkpoint_intent import CheckpointIntent
        from scrapers.checkpoint_coverage import (
            validate_coverage_evidence,
            result_digest,
        )
        from scrapers.storage.checkpoints import CheckpointAdvance

        row = self.validate_run(
            run_id=result.run_id,
            source_name=result.source_name,
        )

        metadata = row.get("metadata") or {}

        raw_intent = metadata.get("checkpoint_intent")
        evidence = metadata.get("checkpoint_coverage")

        if raw_intent is None:

            if evidence is not None:
                raise RuntimeError(
                    "Coverage exists without checkpoint intent"
                )

            return None

        intent = CheckpointIntent.from_metadata(
            raw_intent
        )

        intent.validate_binding(
            run_id=row["run_id"],
            source_name=row["source_name"],
            collection_scope=row["collection_scope"],
        )

        if evidence is None:
            return None

        if self.snapshot_store is None:
            raise RuntimeError(
                "Checkpoint requires durable snapshot storage"
            )

        snapshot = self.snapshot_store.load(
            result.run_id
        )

        if not validate_coverage_evidence(
            intent=intent,
            result=snapshot,
            metadata=evidence,
        ):
            return None

        if result_digest(snapshot) != result_digest(result):
            raise RuntimeError(
                "Snapshot and collection result mismatch"
            )

        if result_digest(prepared) != result_digest(result):
            return None

        return CheckpointAdvance(
            checkpoint_type="timestamp",
            checkpoint_value={
                "timestamp": (
                    intent.target_watermark.isoformat()
                ),
            },
            expected_previous_run_id=intent.previous_run_id,
        )


    def persist_collection(
        self,
        result: CollectionResult,
    ) -> ExecutionResult:

        if not isinstance(result, CollectionResult):

            raise TypeError(
                "Expected a CollectionResult"
            )

        from scrapers.storage.connection_context import (
            get_protected_connection,
            ProtectedConnectionError,
        )

        if self.recovery_lock is not None:

            protected = get_protected_connection()

            if protected is None:

                with self._acquire_run_lock(result.run_id):
                    return self.persist_collection(result)

            if (
                protected.storage is not self.storage
                or protected.run_id != result.run_id
            ):
                raise ProtectedConnectionError(
                    "Protected run identity mismatch"
                )

        from contextlib import nullcontext

        from scrapers.storage.persistence_guard import (
            persistence_guard,
        )

        guard = (
            persistence_guard(
                self.storage,
                result.run_id,
            )
            if self.recovery_lock is not None
            else nullcontext()
        )

        stage = "preparation"

        try:

            prepared = self.prepare_collection(
                result
            )

            # Persistent execution always requires
            # a configured rejection policy.

            if self.rejection_policy is None:

                raise RuntimeError(
                    "Rejection policy is required"
                )

            # Preflight rejected evidence before
            # writing any accepted opportunities.

            for record in prepared.invalid_records:

                self.rejection_policy.sanitize(
                    record
                )

            stage = "snapshot_persistence"

            if self.snapshot_store is not None:

                self.snapshot_store.save(result)

            stage = "checkpoint_resolution"
            with guard:
                stage = "checkpoint_resolution"

                checkpoint = self.resolve_checkpoint_advance(
                    result=result,
                    prepared=prepared,
                )

                stage = "accepted_persistence"

                accepted = self.persist_accepted(
                    prepared
                )

                stage = "rejected_persistence"

                rejected = self.persist_rejected(
                    prepared
                )

                received = (
                    accepted.received
                    + rejected.received
                )

                status = prepared.status.value

                error_message = (
                    None
                    if prepared.status == CollectionStatus.COMPLETED
                    else (
                        "Collection stopped: "
                        f"{prepared.stop_reason.value}"
                    )
                )

                stage = "finalization"

                checkpoint_arguments = {}

                if (
                    checkpoint is not None
                    and received == prepared.accepted_count
                    and prepared.rejected_count == 0
                ):

                    checkpoint_arguments = {
                        "checkpoint": checkpoint,
                        "skip_unsafe_checkpoint": True,
                        "skip_checkpoint_conflict": True,
                    }

                finalized = self.run_recovery.finish_run(
                    run_id=prepared.run_id,
                    status=status,
                    received=received,
                    error_message=error_message,
                    **checkpoint_arguments,
                )

                return ExecutionResult(
                    run_id=prepared.run_id,
                    collection_status=prepared.status,
                    stop_reason=prepared.stop_reason,
                    accepted=accepted,
                    rejected=rejected,
                    finalized_run=finalized,
                )

        except Exception as error:

            # Do not guess whether a database commit
            # succeeded after a connection failure.
            # Preserve the run and original evidence.

            raise IngestionExecutionError(
                run_id=result.run_id,
                stage=stage,
                collection_result=result,
            ) from error

    @contextmanager
    def _acquire_run_lock(self, run_id: UUID):

        if self.recovery_lock is None:
            yield
            return

        acquired = False

        try:
            with self.recovery_lock.acquire(
                run_id,
                bind_connection=True,
            ):
                acquired = True
                yield

        except Exception as error:

            if acquired:
                raise

            raise IngestionExecutionError(
                run_id=run_id,
                stage="recovery_lock",
            ) from error

    def recover(
        self,
        *,
        run_id: UUID,
    ) -> RecoveryResult:

        from scrapers.storage.collection_snapshot import (
            SnapshotNotFoundError,
        )

        if not isinstance(run_id, UUID):

            raise TypeError(
                "run_id must be a UUID"
            )

        if self.snapshot_store is None:

            raise RuntimeError(
                "Snapshot store is required for recovery"
            )

        if self.rejection_policy is None:

            raise RuntimeError(
                "Rejection policy is required for recovery"
            )

        with self._acquire_run_lock(run_id):

            stage = "snapshot_loading"

            result = None

            try:

                try:

                    result = self.snapshot_store.load(
                        run_id
                    )

                except SnapshotNotFoundError:

                    run = self.retry_policy.execute(
                        lambda: self.runs.get_run(run_id)
                    )

                    if run is None:

                        raise

                    if run["status"] != "completed":

                        raise

                    stage = "recovery_validation"

                    if run["run_id"] != run_id:

                        raise ValueError(
                            "Collection run identity mismatch"
                        )

                    finished_at = run.get(
                        "finished_at"
                    )

                    if finished_at is None:

                        raise ValueError(
                            "Completed run has no finalization timestamp"
                        )

                    return RecoveryResult(
                        run_id=run_id,
                        collection_status=CollectionStatus.COMPLETED,
                        stop_reason=None,
                        finalized_run=run,
                        collection_result=None,
                        already_finalized=True,
                    )

                stage = "recovery_validation"

                run = self.retry_policy.execute(
                    lambda: self.runs.get_run(run_id)
                )

                if run is None:

                    raise ValueError(
                        "Collection run does not exist"
                    )

                if run["run_id"] != run_id:

                    raise ValueError(
                        "Collection run identity mismatch"
                    )

                if run["source_name"] != result.source_name:

                    raise ValueError(
                        "Collection source does not match run"
                    )

                if run["status"] != "running":

                    if run["status"] not in {
                        "completed",
                        "partial",
                        "failed",
                        "aborted",
                    }:

                        raise ValueError(
                            "Unsupported collection run status"
                        )

                    if run["status"] != result.status.value:

                        raise ValueError(
                            "Finalized run status does not match snapshot"
                        )

                    return RecoveryResult(
                        run_id=run_id,
                        collection_status=result.status,
                        stop_reason=result.stop_reason,
                        finalized_run=run,
                        collection_result=result,
                        already_finalized=True,
                    )

            except Exception as error:

                raise IngestionExecutionError(
                    run_id=run_id,
                    stage=stage,
                    collection_result=result,
                ) from error

            execution = self.persist_collection(
                result
            )

            return RecoveryResult(
                run_id=run_id,
                collection_status=execution.collection_status,
                stop_reason=execution.stop_reason,
                finalized_run=execution.finalized_run,
                collection_result=result,
                already_finalized=False,
                execution=execution,
            )

    def execute(
        self,
        *,
        scraper: BaseScraper,
        collection_mode: str,
        collection_scope: str = "default",
        metadata: dict | None = None,
        run_id: UUID | None = None,
        checkpoint_intent=None,
    ) -> ExecutionResult:

        if not isinstance(scraper, BaseScraper):

            raise TypeError(
                "Expected a BaseScraper instance"
            )

        if self.rejection_policy is None:

            raise RuntimeError(
                "Rejection policy is required"
            )

        if run_id is not None and not isinstance(
            run_id, UUID
        ):

            raise TypeError(
                "run_id must be a UUID"
            )

        requested_run_id = (
            run_id if run_id is not None else uuid4()
        )

        from scrapers.checkpoint_intent import CheckpointIntent

        metadata = dict(metadata or {})

        reserved = {
            "checkpoint_intent",
            "checkpoint_coverage",
            "checkpoint_finalization",
        }

        if reserved.intersection(metadata):
            raise ValueError(
                "Reserved checkpoint metadata fields"
            )

        if checkpoint_intent is not None:

            if not isinstance(
                checkpoint_intent,
                CheckpointIntent,
            ):
                raise TypeError(
                    "Expected CheckpointIntent"
                )

            if self.snapshot_store is None:
                raise RuntimeError(
                    "Incremental execution requires snapshots"
                )

            if self.recovery_lock is None:
                raise RuntimeError(
                    "Incremental execution requires recovery lock"
                )

            checkpoint_intent.validate_binding(
                run_id=requested_run_id,
                source_name=scraper.source_name,
                collection_scope=collection_scope,
            )

            if collection_mode != "api":
                raise ValueError(
                    "Incremental execution requires API mode"
                )

            if (
                getattr(scraper, "incremental_window", None)
                != checkpoint_intent.window
            ):
                raise ValueError(
                    "Scraper incremental window mismatch"
                )

            if (
                getattr(scraper, "endpoint", None)
                != collection_scope
            ):
                raise ValueError(
                    "Scraper endpoint mismatch"
                )

            self.validate_previous_checkpoint(
                checkpoint_intent
            )

            metadata["checkpoint_intent"] = (
                checkpoint_intent.to_metadata()
            )

        with self._acquire_run_lock(requested_run_id):
            try:

                active_run_id = self.start_collection(
                    scraper=scraper,
                    collection_mode=collection_mode,
                    collection_scope=collection_scope,
                    metadata=metadata,
                    run_id=requested_run_id,
                )

            except Exception as error:

                raise IngestionExecutionError(
                    run_id=requested_run_id,
                    stage="run_creation",
                ) from error

            if active_run_id != requested_run_id:

                raise IngestionExecutionError(
                    run_id=requested_run_id,
                    stage="run_identity",
                )

            try:

                result = self.collect(
                    scraper=scraper,
                    run_id=active_run_id,
                )

            except KeyboardInterrupt:

                result = scraper.last_result

                if (
                    isinstance(result, CollectionResult)
                    and result.run_id == active_run_id
                    and result.source_name == scraper.source_name
                    and result.status == CollectionStatus.ABORTED
                ):

                    self.persist_collection(result)

                raise

            except Exception as error:

                result = scraper.last_result

                if (
                    isinstance(result, CollectionResult)
                    and result.run_id == active_run_id
                    and result.source_name == scraper.source_name
                    and result.status in {
                        CollectionStatus.FAILED,
                        CollectionStatus.PARTIAL,
                    }
                ):

                    self.persist_collection(result)

                raise IngestionExecutionError(
                    run_id=active_run_id,
                    stage="collection",
                    collection_result=(
                        result
                        if isinstance(result, CollectionResult)
                        and result.run_id == active_run_id
                        and result.source_name == scraper.source_name
                        else None
                    ),
                ) from error

            if checkpoint_intent is not None:

                from scrapers.checkpoint_coverage import (
                    create_coverage_evidence,
                )

                try:

                    evidence = create_coverage_evidence(
                        intent=checkpoint_intent,
                        result=result,
                        scraper=scraper,
                    )

                    if evidence is not None:

                        self.snapshot_store.save(result)

                        self.retry_policy.execute(
                            lambda: self.runs.seal_checkpoint_coverage(
                                intent=checkpoint_intent,
                                result=result,
                                evidence=evidence,
                            )
                        )

                except Exception as error:

                    raise IngestionExecutionError(
                        run_id=result.run_id,
                        stage="checkpoint_coverage",
                        collection_result=result,
                    ) from error

            return self.persist_collection(result)


    @staticmethod
    def is_recoverable_failure(error):

        from scrapers.storage.retry_policy import (
            is_retryable_database_error,
        )

        from scrapers.storage.connection_context import (
            ProtectedConnectionError,
            ProtectedConnectionLostError,
        )

        current = error
        visited = set()
        retryable = False

        while (
            current is not None
            and id(current) not in visited
        ):

            visited.add(id(current))

            if isinstance(
                current,
                ProtectedConnectionLostError,
            ):

                retryable = True

            elif isinstance(
                current,
                ProtectedConnectionError,
            ):

                return False

            elif is_retryable_database_error(current):

                retryable = True

            current = current.__cause__

        return retryable

    def recover_with_retry(self, *, run_id: UUID):

        from time import sleep

        from scrapers.storage.connection_context import (
            get_protected_connection,
        )

        if get_protected_connection() is not None:

            raise RuntimeError(
                "Recovery retry requires an independent session"
            )

        for attempt in range(
            1,
            self.retry_policy.max_attempts + 1,
        ):

            try:

                return self.recover(run_id=run_id)

            except IngestionExecutionError as error:

                if (
                    not self.is_recoverable_failure(error)
                    or attempt == self.retry_policy.max_attempts
                ):

                    raise

                if get_protected_connection() is not None:

                    raise RuntimeError(
                        "Protected connection was not released"
                    ) from error

                sleep(
                    self.retry_policy.initial_delay
                    * 2 ** (attempt - 1)
                )

        raise RuntimeError("Unreachable recovery state")

    def execute_with_recovery(self, **kwargs):

        from scrapers.checkpoint_coverage import (
            result_digest,
        )

        from scrapers.storage.connection_context import (
            get_protected_connection,
        )

        from scrapers.storage.collection_snapshot import (
            SnapshotNotFoundError,
        )

        try:

            return self.execute(**kwargs)

        except IngestionExecutionError as error:

            if error.stage not in {
                "checkpoint_resolution",
                "accepted_persistence",
                "rejected_persistence",
                "finalization",
            }:

                raise

            if not self.is_recoverable_failure(error):

                raise

            if (
                self.snapshot_store is None
                or self.recovery_lock is None
                or get_protected_connection() is not None
            ):

                raise

            expected_run_id = kwargs.get("run_id")

            if (
                expected_run_id is not None
                and error.run_id != expected_run_id
            ):

                raise

            scraper = kwargs["scraper"]

            original_result = scraper.last_result

            if not isinstance(
                original_result,
                CollectionResult,
            ):

                raise

            if (
                original_result.run_id != error.run_id
                or original_result.source_name
                    != scraper.source_name
            ):

                raise

            try:

                snapshot = self.snapshot_store.load(
                    error.run_id
                )

            except SnapshotNotFoundError:

                raise error

            if result_digest(snapshot) != result_digest(
                original_result
            ):

                raise RuntimeError(
                    "Recovery snapshot identity mismatch"
                ) from error

            return self.recover_with_retry(
                run_id=error.run_id
            )
