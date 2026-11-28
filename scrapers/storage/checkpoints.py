import json

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from scrapers.source_config import get_source_config

from scrapers.storage.postgres import PostgresStorage
from psycopg.pq import TransactionStatus


CHECKPOINT_TYPES = frozenset({
    "timestamp",
    "cursor",
    "numeric_id",
    "page_number",
    "composite",
})


class CheckpointError(RuntimeError):
    pass


class CheckpointConflictError(CheckpointError):
    pass


class ConcurrentCheckpointError(CheckpointConflictError):
    pass


def validate_source_scope(
    source_name: str,
    collection_scope: str,
) -> None:

    config = get_source_config(source_name)

    if not config.enabled:
        raise ValueError("Source is disabled")

    if (
        not isinstance(collection_scope, str)
        or not collection_scope.strip()
        or collection_scope != collection_scope.strip()
        or "\x00" in collection_scope
    ):
        raise ValueError("Invalid collection scope")


def normalize_checkpoint_value(
    checkpoint_type: str,
    value: dict,
) -> dict:

    if checkpoint_type not in CHECKPOINT_TYPES:
        raise ValueError("Unsupported checkpoint type")

    if not isinstance(value, dict) or not value:
        raise ValueError(
            "Checkpoint value must be a non-empty dictionary"
        )

    def validate_json(item):

        if isinstance(item, dict):

            for key, child in item.items():

                if not isinstance(key, str):
                    raise ValueError(
                        "JSON object keys must be strings"
                    )

                validate_json(key)
                validate_json(child)

        elif isinstance(item, list):

            for child in item:
                validate_json(child)

        elif isinstance(item, str):

            if "\x00" in item:
                raise ValueError(
                    "JSON strings cannot contain NUL"
                )

        elif item is not None and type(item) not in (
            int, float, bool
        ):

            raise ValueError("Unsupported JSON value")

    validate_json(value)

    try:

        normalized = json.loads(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
            )
        )

    except (TypeError, ValueError) as error:

        raise ValueError(
            "Checkpoint value must contain valid JSON"
        ) from error

    if checkpoint_type == "timestamp":

        if set(normalized) != {"timestamp"}:
            raise ValueError(
                "Expected a timestamp field"
            )

        raw = normalized["timestamp"]

        if not isinstance(raw, str):
            raise ValueError(
                "Timestamp must be an ISO string"
            )

        timestamp = datetime.fromisoformat(raw)

        if (
            timestamp.tzinfo is None
            or timestamp.utcoffset() is None
        ):
            raise ValueError(
                "Checkpoint timestamp must be timezone-aware"
            )

        normalized["timestamp"] = (
            timestamp.astimezone(timezone.utc).isoformat()
        )

    elif checkpoint_type == "cursor":

        if set(normalized) != {"cursor"}:
            raise ValueError("Expected a cursor field")

        cursor = normalized["cursor"]

        if (
            not isinstance(cursor, str)
            or not cursor.strip()
        ):
            raise ValueError(
                "Cursor must be a non-empty string"
            )

    elif checkpoint_type == "numeric_id":

        if set(normalized) != {"id"}:
            raise ValueError("Expected an id field")

        identifier = normalized["id"]

        if type(identifier) is not int or identifier < 0:
            raise ValueError(
                "Numeric ID must be a non-negative integer"
            )

    elif checkpoint_type == "page_number":

        if set(normalized) != {"page"}:
            raise ValueError("Expected a page field")

        page = normalized["page"]

        if type(page) is not int or page < 1:
            raise ValueError(
                "Page number must be a positive integer"
            )

    return normalized


@dataclass(frozen=True, slots=True)
class CheckpointAdvance:

    checkpoint_type: str
    checkpoint_value: dict
    expected_previous_run_id: UUID | None

    def __post_init__(self) -> None:

        if (
            self.expected_previous_run_id is not None
            and not isinstance(
                self.expected_previous_run_id,
                UUID,
            )
        ):
            raise ValueError(
                "Expected previous run ID must be a UUID"
            )

        normalized = normalize_checkpoint_value(
            self.checkpoint_type,
            self.checkpoint_value,
        )

        object.__setattr__(
            self,
            "checkpoint_value",
            normalized,
        )


class CheckpointRepository:

    def __init__(
        self,
        storage: PostgresStorage,
    ) -> None:

        self.storage = storage

    def get_checkpoint(
        self,
        *,
        source_name: str,
        collection_scope: str = "default",
    ) -> dict | None:

        validate_source_scope(
            source_name,
            collection_scope,
        )

        with self.storage.transaction(
            read_only=True
        ) as conn:

            return conn.execute(
                """
                SELECT *
                FROM bronze.source_checkpoints
                WHERE source_name = %s
                  AND collection_scope = %s
                """,
                (
                    source_name,
                    collection_scope,
                ),
            ).fetchone()

    @staticmethod
    def _advance(
        connection: Connection,
        *,
        run_id: UUID,
        advance: CheckpointAdvance,
    ) -> dict:

        if (
            connection.closed
            or connection.info.transaction_status
            != TransactionStatus.INTRANS
        ):
            raise CheckpointError(
                "An active transaction is required"
            )

        if not isinstance(run_id, UUID):
            raise ValueError("run_id must be a UUID")

        if not isinstance(advance, CheckpointAdvance):
            raise TypeError(
                "advance must be a CheckpointAdvance"
            )

        value = normalize_checkpoint_value(
            advance.checkpoint_type,
            advance.checkpoint_value,
        )

        run = connection.execute(
            """
            SELECT *
            FROM bronze.collection_runs
            WHERE run_id = %s
            FOR UPDATE
            """,
            (run_id,),
        ).fetchone()

        if run is None:
            raise CheckpointError(
                "Collection run not found"
            )

        if run["status"] != "completed":
            raise CheckpointError(
                "Checkpoint requires a completed run"
            )

        processed = sum(
            run[f"records_{field}"]
            for field in (
                "inserted",
                "updated",
                "unchanged",
                "invalid",
                "stale",
                "conflicted",
            )
        )

        if processed != run["records_received"]:
            raise CheckpointError(
                "Run contains unprocessed records"
            )

        if (
            run["records_invalid"] > 0
            or run["records_conflicted"] > 0
            or run["records_stale"] > 0
        ):
            raise CheckpointError(
                "Checkpoint requires zero invalid, "
                "stale and conflicted records"
            )

        source_name = run["source_name"]
        collection_scope = run["collection_scope"]

        validate_source_scope(
            source_name,
            collection_scope,
        )

        expected = advance.expected_previous_run_id

        current = connection.execute(
            """
            SELECT *
            FROM bronze.source_checkpoints
            WHERE source_name = %s
              AND collection_scope = %s
            FOR UPDATE
            """,
            (
                source_name,
                collection_scope,
            ),
        ).fetchone()

        if current is None:

            if expected is not None:
                raise ConcurrentCheckpointError(
                    "Expected checkpoint does not exist"
                )

            result = connection.execute(
                """
                INSERT INTO bronze.source_checkpoints (
                    source_name,
                    collection_scope,
                    checkpoint_type,
                    checkpoint_value,
                    last_successful_run_id
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (
                    source_name,
                    collection_scope
                )
                DO NOTHING
                RETURNING *
                """,
                (
                    source_name,
                    collection_scope,
                    advance.checkpoint_type,
                    Jsonb(value),
                    run_id,
                ),
            ).fetchone()

            if result is None:
                raise ConcurrentCheckpointError(
                    "Checkpoint was created concurrently"
                )

            return result

        if current["last_successful_run_id"] == run_id:

            if (
                current["checkpoint_type"]
                == advance.checkpoint_type
                and current["checkpoint_value"] == value
            ):
                return current

            raise CheckpointConflictError(
                "Run already advanced a different checkpoint"
            )

        if current["last_successful_run_id"] != expected:
            raise ConcurrentCheckpointError(
                "Checkpoint changed since collection started"
            )

        raw_intent = (run.get("metadata") or {}).get(
            "checkpoint_intent"
        )

        if raw_intent is not None:

            from scrapers.checkpoint_intent import CheckpointIntent

            intent = CheckpointIntent.from_metadata(raw_intent)

            intent.validate_binding(
                run_id=run_id,
                source_name=source_name,
                collection_scope=collection_scope,
            )

            if (
                intent.previous_run_id != expected
                or advance.checkpoint_type != "timestamp"
                or current["checkpoint_type"] != "timestamp"
                or datetime.fromisoformat(value["timestamp"])
                != intent.target_watermark
                or datetime.fromisoformat(
                    current["checkpoint_value"]["timestamp"]
                ) != intent.previous_watermark
            ):
                raise CheckpointError(
                    "Persisted checkpoint intent mismatch"
                )

        previous = connection.execute(
            """
            SELECT
                source_name,
                collection_scope,
                started_at,
                status
            FROM bronze.collection_runs
            WHERE run_id = %s
            """,
            (expected,),
        ).fetchone()

        if (
            previous is None
            or previous["status"] != "completed"
            or previous["source_name"] != source_name
            or previous["collection_scope"] != collection_scope
        ):
            raise CheckpointError(
                "Invalid previous checkpoint run"
            )

        if run["started_at"] <= previous["started_at"]:
            raise CheckpointConflictError(
                "Older run cannot replace a newer checkpoint"
            )

        if (
            current["checkpoint_type"]
            != advance.checkpoint_type
        ):
            raise CheckpointConflictError(
                "Checkpoint type cannot change automatically"
            )

        old_value = current["checkpoint_value"]
        kind = advance.checkpoint_type

        if kind == "timestamp":

            if datetime.fromisoformat(
                value["timestamp"]
            ) < datetime.fromisoformat(
                old_value["timestamp"]
            ):
                raise CheckpointConflictError(
                    "Timestamp checkpoint cannot move backwards"
                )

        elif kind == "numeric_id":

            if value["id"] < old_value["id"]:
                raise CheckpointConflictError(
                    "Numeric checkpoint cannot move backwards"
                )

        elif kind == "page_number":

            if value["page"] < old_value["page"]:
                raise CheckpointConflictError(
                    "Page checkpoint cannot move backwards"
                )

        result = connection.execute(
            """
            UPDATE bronze.source_checkpoints
            SET
                checkpoint_value = %s,
                last_successful_run_id = %s,
                updated_at = GREATEST(
                    clock_timestamp(),
                    updated_at
                )
            WHERE checkpoint_id = %s
              AND last_successful_run_id = %s
            RETURNING *
            """,
            (
                Jsonb(value),
                run_id,
                current["checkpoint_id"],
                expected,
            ),
        ).fetchone()

        if result is None:
            raise ConcurrentCheckpointError(
                "Checkpoint update failed"
            )

        return result
