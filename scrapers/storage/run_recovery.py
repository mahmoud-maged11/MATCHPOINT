import json

import psycopg

from uuid import UUID

from scrapers.storage.collection_runs import (
    CONTRACT_VERSION,
    CollectionRunManager,
)

from scrapers.utils.hashing import HASH_VERSION
from scrapers.storage.checkpoints import CheckpointAdvance

from scrapers.storage.counters import (
    RunCounterRepository,
)

from scrapers.storage.retry_policy import (
    RetryPolicy,
    is_retryable_database_error,
)


class RunRecoveryError(RuntimeError):
    pass


COUNTER_FIELDS = (
    "received",
    "inserted",
    "updated",
    "unchanged",
    "invalid",
    "stale",
    "conflicted",
)


class RunRecovery:

    def __init__(
        self,
        manager: CollectionRunManager,
        retry_policy: RetryPolicy,
    ):

        self.manager = manager
        self.retry_policy = retry_policy

    @staticmethod
    def validate_creation(
        row: dict,
        *,
        run_id: UUID,
        source_name: str,
        collection_mode: str,
        collection_scope: str,
        metadata: dict,
    ) -> UUID:

        expected = {
            "run_id": run_id,
            "source_name": source_name,
            "collection_mode": collection_mode,
            "collection_scope": collection_scope,
            "contract_version": CONTRACT_VERSION,
            "hash_version": HASH_VERSION,
            "metadata": metadata,
            "status": "running",
            "finished_at": None,
            "error_message": None,
        }

        for field, value in expected.items():

            if field not in row or row[field] != value:

                raise RunRecoveryError(
                    f"Run creation mismatch: {field}"
                )

        for field in COUNTER_FIELDS:

            if row.get(f"records_{field}") != 0:

                raise RunRecoveryError(
                    "Recovered run contains finalized counters"
                )

        if row.get("started_at") is None:

            raise RunRecoveryError(
                "Recovered run has no start timestamp"
            )

        return run_id

    def start_run(
        self,
        *,
        run_id: UUID,
        source_name: str,
        collection_mode: str,
        collection_scope: str = "default",
        metadata: dict | None = None,
    ) -> UUID:

        if not isinstance(run_id, UUID):

            raise TypeError("run_id must be a UUID")

        if metadata is not None and not isinstance(
            metadata, dict
        ):

            raise TypeError("metadata must be a dictionary")

        normalized_metadata = json.loads(
            json.dumps(
                metadata if metadata is not None else {},
                allow_nan=False,
            )
        )

        arguments = {
            "run_id": run_id,
            "source_name": source_name,
            "collection_mode": collection_mode,
            "collection_scope": collection_scope,
            "metadata": normalized_metadata,
        }

        attempted = False

        def operation():

            nonlocal attempted

            if attempted:

                row = self.manager.get_run(run_id)

                if row is not None:

                    return self.validate_creation(
                        row,
                        **arguments,
                    )

            try:

                return self.manager.start_run(
                    **arguments
                )

            except psycopg.Error as error:

                if is_retryable_database_error(error):

                    attempted = True

                raise

        return self.retry_policy.execute(operation)

    def verify_finalization(
        self,
        *,
        run_id: UUID,
        status: str,
        received: int,
        error_message: str | None,
        checkpoint: CheckpointAdvance | None = None,
        skip_unsafe_checkpoint: bool = False,
        skip_checkpoint_conflict: bool = False,
    ) -> dict | None:

        with self.manager.storage.transaction(
            read_only=True
        ) as connection:

            row = connection.execute(
                """
                SELECT *
                FROM bronze.collection_runs
                WHERE run_id = %s
                """,
                (run_id,),
            ).fetchone()

            if row is None:

                raise RunRecoveryError(
                    "Run missing during finalization recovery"
                )

            if row["status"] == "running":

                return None

            expected = {
                "run_id": run_id,
                "status": status,
                "records_received": received,
                "error_message": error_message,
                "contract_version": CONTRACT_VERSION,
                "hash_version": HASH_VERSION,
            }

            for field, value in expected.items():

                if field not in row or row[field] != value:

                    raise RunRecoveryError(
                        f"Finalization mismatch: {field}"
                    )

            if (
                row.get("started_at") is None
                or row.get("finished_at") is None
                or row["finished_at"] < row["started_at"]
            ):

                raise RunRecoveryError(
                    "Invalid finalization timestamps"
                )

            actual = RunCounterRepository.calculate(
                connection,
                run_id=run_id,
                received=received,
            )

            for field in COUNTER_FIELDS:

                if row.get(f"records_{field}") != getattr(
                    actual,
                    field,
                ):

                    raise RunRecoveryError(
                        f"Finalized counter mismatch: {field}"
                    )

            if (
                status == "completed"
                and actual.unprocessed != 0
            ):

                raise RunRecoveryError(
                    "Completed run contains unprocessed records"
                )

            if checkpoint is not None:

                unsafe = (
                    actual.invalid > 0
                    or actual.stale > 0
                    or actual.conflicted > 0
                )

                if unsafe and not skip_unsafe_checkpoint:
                    raise RunRecoveryError(
                        "Unsafe checkpoint finalization"
                    )

                expected_receipt = {
                    "version": 1,
                    "outcome": (
                        "skipped_unsafe_counters"
                        if unsafe
                        else "advanced"
                    ),
                    "checkpoint_type": checkpoint.checkpoint_type,
                    "checkpoint_value": checkpoint.checkpoint_value,
                    "expected_previous_run_id": (
                        str(checkpoint.expected_previous_run_id)
                        if checkpoint.expected_previous_run_id
                        is not None
                        else None
                    ),
                }

                receipt = row["metadata"].get(
                    "checkpoint_finalization"
                )

                allowed_receipts = [expected_receipt]

                if skip_checkpoint_conflict and not unsafe:

                    allowed_receipts.append({
                        **expected_receipt,
                        "outcome": "skipped_checkpoint_conflict",
                    })

                if receipt not in allowed_receipts:
                    raise RunRecoveryError(
                        "Checkpoint finalization receipt mismatch"
                    )

            return row

    def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        received: int,
        error_message: str | None = None,
        checkpoint: CheckpointAdvance | None = None,
        skip_unsafe_checkpoint: bool = False,
        skip_checkpoint_conflict: bool = False,
    ) -> dict:

        arguments = {
            "run_id": run_id,
            "status": status,
            "received": received,
            "error_message": error_message,
        }

        if checkpoint is not None:
            arguments["checkpoint"] = checkpoint
            arguments["skip_unsafe_checkpoint"] = (
                skip_unsafe_checkpoint
            )

            if skip_checkpoint_conflict:

                arguments["skip_checkpoint_conflict"] = True

        attempted = False

        def operation():

            nonlocal attempted

            if attempted:

                recovered = self.verify_finalization(
                    **arguments
                )

                if recovered is not None:

                    return recovered

            try:

                return self.manager.finish_run(
                    **arguments
                )

            except psycopg.Error as error:

                if is_retryable_database_error(error):

                    attempted = True

                raise

        return self.retry_policy.execute(operation)
