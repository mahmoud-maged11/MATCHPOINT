import os

from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from psycopg import sql

from scrapers.models import Opportunity

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.collection_runs import (
    CollectionRunManager,
    CollectionRunError,
    RunCounters,
)

from scrapers.storage.opportunities import (
    OpportunityRepository,
)

from scrapers.storage.invalid_records import (
    InvalidRecordRepository,
)

from scrapers.storage.counters import (
    RunCounterRepository,
)


pytestmark = pytest.mark.skipif(
    os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1",
    reason="Requires isolated ingestion test database",
)


@pytest.fixture
def context():

    storage = PostgresStorage(
        PostgresSettings.from_config(
            host="127.0.0.1",
            database="matchpoint_ingestion_test",
        )
    )

    assert storage.health_check()["database"] == (
        "matchpoint_ingestion_test"
    )

    manager = CollectionRunManager(storage)
    repository = OpportunityRepository(storage)
    invalid = InvalidRecordRepository(storage)
    counter = RunCounterRepository(storage)

    run_ids = []

    prefix = uuid4().hex

    observed_at = (
        datetime.now(timezone.utc)
        - timedelta(hours=2)
    )

    def start_run():

        run_id = uuid4()

        run_ids.append(run_id)

        manager.start_run(
            run_id=run_id,
            source_name="wuzzuf",
            collection_mode="api",
            collection_scope="counter_integrity_test",
        )

        return run_id

    def opportunity(suffix, **updates):

        identifier = f"{prefix}{suffix}"

        return Opportunity.model_validate({
            "source_name": "wuzzuf",
            "source_opportunity_id": identifier,
            "source_url": (
                f"https://wuzzuf.net/jobs/p/{identifier}"
            ),
            "title": "Data Engineer",
            "opportunity_type": "job",
            "collected_at": observed_at,
            "raw_payload": {"id": identifier},
            **updates,
        })

    try:

        seed_run = start_run()

        for suffix in ("B", "C", "D", "E"):

            result = repository.ingest(
                opportunity(suffix),
                seed_run,
            )

            assert result.outcome == "inserted"

        manager.finish_run(
            run_id=seed_run,
            status="completed",
            received=4,
        )

        run_id = start_run()

        records = [
            (
                opportunity("A"),
                "inserted",
            ),
            (
                opportunity(
                    "B",
                    title="Senior Data Engineer",
                    collected_at=(
                        observed_at + timedelta(hours=1)
                    ),
                ),
                "updated",
            ),
            (
                opportunity(
                    "C",
                    collected_at=(
                        observed_at + timedelta(hours=1)
                    ),
                ),
                "unchanged",
            ),
            (
                opportunity(
                    "D",
                    collected_at=(
                        observed_at - timedelta(hours=1)
                    ),
                ),
                "stale",
            ),
            (
                opportunity(
                    "E",
                    title="Equal timestamp conflict",
                ),
                "conflicted",
            ),
            (
                opportunity(
                    "A",
                    title="Same run conflict",
                ),
                "conflicted",
            ),
        ]

        for record, expected in records:

            result = repository.ingest(
                record,
                run_id,
            )

            assert result.outcome == expected

        rejection = {
            "run_id": run_id,
            "source_name": "wuzzuf",
            "failure_stage": "validation",
            "error_code": "MissingTitle",
            "error_message": "Required title is missing",
            "record_payload": {
                "id": f"{prefix}F",
                "title": None,
            },
        }

        assert invalid.record(**rejection).inserted

        expected = RunCounters(
            received=7,
            inserted=1,
            updated=1,
            unchanged=1,
            stale=1,
            conflicted=2,
            invalid=1,
        )

        yield {
            "storage": storage,
            "manager": manager,
            "repository": repository,
            "invalid": invalid,
            "counter": counter,
            "run_id": run_id,
            "records": records,
            "rejection": rejection,
            "expected": expected,
        }

    finally:

        with storage.transaction() as conn:

            for table in (
                "invalid_records",
                "ingestion_observations",
                "source_listing_history",
            ):

                conn.execute(
                    sql.SQL(
                        """
                        DELETE FROM bronze.{}
                        WHERE collection_run_id = ANY(%s::uuid[])
                        """
                    ).format(sql.Identifier(table)),
                    (run_ids,),
                )

            conn.execute(
                """
                DELETE FROM bronze.source_listings
                WHERE source_name = 'wuzzuf'
                  AND source_opportunity_id LIKE %s
                """,
                (prefix + "%",),
            )

            conn.execute(
                """
                DELETE FROM bronze.collection_runs
                WHERE run_id = ANY(%s::uuid[])
                """,
                (run_ids,),
            )


def test_all_counter_outcomes(context):

    actual = context["counter"].reconcile(
        run_id=context["run_id"],
        received=7,
    )

    assert actual == context["expected"]
    assert actual.processed == 7
    assert actual.unprocessed == 0


def test_all_outcomes_finalization(context):

    result = context["manager"].finish_run(
        run_id=context["run_id"],
        status="completed",
        received=7,
    )

    assert result["status"] == "completed"

    expected = context["expected"]

    for field in (
        "received",
        "inserted",
        "updated",
        "unchanged",
        "invalid",
        "stale",
        "conflicted",
    ):

        assert result[f"records_{field}"] == getattr(
            expected,
            field,
        )


def test_retries_preserve_all_counters(context):

    for record, _ in context["records"]:

        context["repository"].ingest(
            record,
            context["run_id"],
        )

    assert not context["invalid"].record(
        **context["rejection"]
    ).inserted

    actual = context["counter"].reconcile(
        run_id=context["run_id"],
        received=7,
    )

    assert actual == context["expected"]


def test_unprocessed_records_remain_visible(context):

    result = context["counter"].reconcile(
        run_id=context["run_id"],
        received=10,
    )

    assert result.processed == 7
    assert result.unprocessed == 3


def test_underreported_received_rejected(context):

    with pytest.raises(CollectionRunError):

        context["counter"].reconcile(
            run_id=context["run_id"],
            received=6,
        )


def test_missing_run_rejected(context):

    with pytest.raises(CollectionRunError):

        context["counter"].reconcile(
            run_id=uuid4(),
            received=0,
        )


CORRUPTIONS = [
    (
        "missing_equal_conflict",
        """
        DELETE FROM bronze.invalid_records
        WHERE collection_run_id = %s
          AND error_code = 'EqualTimestampContentMismatch'
        """,
    ),
    (
        "wrong_equal_listing_id",
        """
        UPDATE bronze.invalid_records
        SET error_details = jsonb_set(
            error_details,
            '{source_listing_id}',
            to_jsonb('invalid-listing-id'::TEXT)
        )
        WHERE collection_run_id = %s
          AND error_code = 'EqualTimestampContentMismatch'
        """,
    ),
    (
        "wrong_equal_observation_hash",
        """
        UPDATE bronze.invalid_records
        SET record_payload = jsonb_set(
            record_payload,
            '{incoming_observation_hash}',
            to_jsonb(repeat('f', 64))
        )
        WHERE collection_run_id = %s
          AND error_code = 'EqualTimestampContentMismatch'
        """,
    ),
    (
        "wrong_equal_timestamp",
        """
        UPDATE bronze.invalid_records
        SET observed_at = observed_at + INTERVAL '1 second'
        WHERE collection_run_id = %s
          AND error_code = 'EqualTimestampContentMismatch'
        """,
    ),
    (
        "wrong_equal_source_identity",
        """
        UPDATE bronze.invalid_records
        SET source_opportunity_id = 'incorrect-source-id'
        WHERE collection_run_id = %s
          AND error_code = 'EqualTimestampContentMismatch'
        """,
    ),
    (
        "wrong_same_run_previous_hash",
        """
        UPDATE bronze.invalid_records
        SET error_details = jsonb_set(
            error_details,
            '{previous_observation_hash}',
            to_jsonb(repeat('f', 64))
        )
        WHERE collection_run_id = %s
          AND error_code = 'SameRunObservationMismatch'
        """,
    ),
    (
        "same_run_identical_hash",
        """
        UPDATE bronze.invalid_records
        SET record_payload = jsonb_set(
            record_payload,
            '{incoming_observation_hash}',
            error_details -> 'previous_observation_hash'
        )
        WHERE collection_run_id = %s
          AND error_code = 'SameRunObservationMismatch'
        """,
    ),
    (
        "missing_same_run_listing",
        """
        UPDATE bronze.invalid_records
        SET error_details =
            error_details - 'source_listing_id'
        WHERE collection_run_id = %s
          AND error_code = 'SameRunObservationMismatch'
        """,
    ),
    (
        "missing_content_hash",
        """
        UPDATE bronze.invalid_records
        SET record_payload =
            record_payload - 'incoming_content_hash'
        WHERE collection_run_id = %s
          AND error_code = 'SameRunObservationMismatch'
        """,
    ),
    (
        "malformed_incoming_hash",
        """
        UPDATE bronze.invalid_records
        SET record_payload = jsonb_set(
            record_payload,
            '{incoming_observation_hash}',
            to_jsonb('invalid-hash'::TEXT)
        )
        WHERE collection_run_id = %s
          AND error_code = 'SameRunObservationMismatch'
        """,
    ),
    (
        "unexpected_equal_previous_hash",
        """
        UPDATE bronze.invalid_records
        SET error_details = jsonb_set(
            error_details,
            '{previous_observation_hash}',
            to_jsonb(repeat('a', 64))
        )
        WHERE collection_run_id = %s
          AND error_code = 'EqualTimestampContentMismatch'
        """,
    ),
    (
        "duplicate_equal_conflict",
        """
        INSERT INTO bronze.invalid_records (
            collection_run_id,
            source_opportunity_id,
            source_url,
            failure_stage,
            error_code,
            error_message,
            error_details,
            record_payload,
            rejection_hash,
            observed_at
        )
        SELECT
            collection_run_id,
            source_opportunity_id,
            source_url,
            failure_stage,
            error_code,
            error_message,
            error_details,
            record_payload,
            repeat('f', 64),
            observed_at
        FROM bronze.invalid_records
        WHERE collection_run_id = %s
          AND error_code = 'EqualTimestampContentMismatch'
        """,
    ),
]


@pytest.mark.parametrize(
    "name,statement",
    CORRUPTIONS,
    ids=[item[0] for item in CORRUPTIONS],
)
def test_corrupted_conflict_evidence_rejected(
    context,
    name,
    statement,
):

    class ForcedRollback(Exception):
        pass

    run_id = context["run_id"]

    with pytest.raises(ForcedRollback):

        with context["storage"].transaction() as conn:

            conn.execute(
                """
                SELECT run_id
                FROM bronze.collection_runs
                WHERE run_id = %s
                FOR UPDATE
                """,
                (run_id,),
            )

            changed = conn.execute(
                statement,
                (run_id,),
            )

            assert changed.rowcount == 1, name

            with pytest.raises(
                CollectionRunError,
                match="Conflict identity reconciliation failed",
            ):

                context["counter"].calculate(
                    conn,
                    run_id=run_id,
                    received=7,
                )

            raise ForcedRollback()

    actual = context["counter"].reconcile(
        run_id=run_id,
        received=7,
    )

    assert actual == context["expected"]


def test_finalization_rejects_corrupted_evidence(context):

    run_id = context["run_id"]

    before = context["manager"].get_run(run_id)

    with context["storage"].transaction() as conn:

        changed = conn.execute(
            """
            UPDATE bronze.invalid_records
            SET observed_at = observed_at + INTERVAL '1 second'
            WHERE collection_run_id = %s
              AND error_code = 'EqualTimestampContentMismatch'
            """,
            (run_id,),
        )

        assert changed.rowcount == 1

    with pytest.raises(
        CollectionRunError,
        match="Conflict identity reconciliation failed",
    ):

        context["manager"].finish_run(
            run_id=run_id,
            status="completed",
            received=7,
        )

    assert context["manager"].get_run(run_id) == before

    with context["storage"].transaction() as conn:

        conn.execute(
            """
            UPDATE bronze.invalid_records
            SET observed_at = observed_at - INTERVAL '1 second'
            WHERE collection_run_id = %s
              AND error_code = 'EqualTimestampContentMismatch'
            """,
            (run_id,),
        )

    result = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=7,
    )

    assert result["status"] == "completed"
    assert result["records_conflicted"] == 2
