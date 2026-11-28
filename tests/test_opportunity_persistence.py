import os

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

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

from scrapers.storage.identity import SourceIdentityError

from scrapers.utils.hashing import (
    generate_content_hash,
    generate_observation_hash,
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

    assert (
        storage.health_check()["database"]
        == "matchpoint_ingestion_test"
    )

    manager = CollectionRunManager(storage)
    repository = OpportunityRepository(storage)

    identifier = uuid4().hex
    identity_key = f"id:{identifier}"

    run_ids = []

    base = Opportunity(
        source_name="wuzzuf",
        source_opportunity_id=identifier,
        source_url=f"https://wuzzuf.net/jobs/p/{identifier}",
        title="Data Engineer",
        organization="MATCHPOINT",
        opportunity_type="job",
        salary_min=Decimal("10000"),
        salary_max=Decimal("15000"),
        currency="EGP",
        salary_period="monthly",
        required_skills=[],
        categories=None,
        status="active",
        collected_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=3)
        ),
        raw_payload={"id": identifier},
    )

    def changed(**updates):

        return Opportunity.model_validate({
            **base.model_dump(mode="json"),
            **updates,
        })

    def start_run(source="wuzzuf"):

        run_id = uuid4()
        run_ids.append(run_id)

        manager.start_run(
            run_id=run_id,
            source_name=source,
            collection_mode="api",
            collection_scope="pytest_persistence",
            metadata={"test": True},
        )

        return run_id

    def snapshot():

        with storage.transaction(read_only=True) as conn:

            current = conn.execute(
                """
                SELECT *
                FROM bronze.source_listings
                WHERE source_name = %s
                  AND source_identity_key = %s
                """,
                ("wuzzuf", identity_key),
            ).fetchone()

            if current is None:
                return None, [], []

            listing_id = current["source_listing_id"]

            history = conn.execute(
                """
                SELECT *
                FROM bronze.source_listing_history
                WHERE source_listing_id = %s
                ORDER BY content_version
                """,
                (listing_id,),
            ).fetchall()

            observations = conn.execute(
                """
                SELECT *
                FROM bronze.ingestion_observations
                WHERE source_listing_id = %s
                ORDER BY collection_run_id
                """,
                (listing_id,),
            ).fetchall()

            return current, history, observations

    def assert_preserved(before, additional=0):

        after = snapshot()

        assert after[0] == before[0]
        assert after[1] == before[1]

        previous = {
            row["collection_run_id"]: row
            for row in before[2]
        }

        current = {
            row["collection_run_id"]: row
            for row in after[2]
        }

        for run_id, row in previous.items():
            assert current[run_id] == row

        assert len(after[2]) == len(before[2]) + additional

    def assert_ledger(run_id, result, opportunity):

        rows = [
            row
            for row in snapshot()[2]
            if row["collection_run_id"] == run_id
        ]

        assert len(rows) == 1

        assert rows[0]["outcome"] == result.outcome

        assert (
            rows[0]["observation_hash"]
            == generate_observation_hash(opportunity)
        )

        assert (
            rows[0]["observed_at"]
            == opportunity.collected_at
        )

    try:

        yield {
            "storage": storage,
            "manager": manager,
            "repository": repository,
            "base": base,
            "changed": changed,
            "start_run": start_run,
            "snapshot": snapshot,
            "assert_preserved": assert_preserved,
            "assert_ledger": assert_ledger,
        }

    finally:

        with storage.transaction() as conn:

            listings = conn.execute(
                """
                SELECT source_listing_id
                FROM bronze.source_listings
                WHERE last_collection_run_id = ANY(%s::uuid[])
                   OR (
                       source_name = %s
                       AND source_identity_key = %s
                   )
                """,
                (run_ids, "wuzzuf", identity_key),
            ).fetchall()

            for listing in listings:

                listing_id = listing["source_listing_id"]

                conn.execute(
                    """
                    DELETE FROM bronze.ingestion_observations
                    WHERE source_listing_id = %s
                    """,
                    (listing_id,),
                )

                conn.execute(
                    """
                    DELETE FROM bronze.source_listing_history
                    WHERE source_listing_id = %s
                    """,
                    (listing_id,),
                )

                conn.execute(
                    """
                    DELETE FROM bronze.source_listings
                    WHERE source_listing_id = %s
                    """,
                    (listing_id,),
                )

            for run_id in run_ids:

                conn.execute(
                    """
                    DELETE FROM bronze.invalid_records
                    WHERE collection_run_id = %s
                    """,
                    (run_id,),
                )

                conn.execute(
                    """
                    DELETE FROM bronze.collection_runs
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )


@pytest.fixture
def inserted(context):

    run_id = context["start_run"]()

    result = context["repository"].ingest(
        context["base"],
        run_id,
    )

    assert result.outcome == "inserted"

    return run_id, result


def test_insert_new_listing(context, inserted):

    run_id, result = inserted

    current, history, observations = context["snapshot"]()

    assert result.content_version == 1
    assert current["source_listing_id"] == result.source_listing_id
    assert current["content_version"] == 1
    assert current["last_collection_run_id"] == run_id
    assert current["hash_version"] == 1

    assert len(history) == 1
    assert len(observations) == 1

    assert (
        current["content_hash"]
        == generate_content_hash(context["base"])
    )

    context["assert_ledger"](
        run_id, result, context["base"]
    )


def test_null_and_empty_arrays(context, inserted):

    current, _, _ = context["snapshot"]()

    assert current["required_skills"] == []
    assert current["categories"] is None


def test_unchanged_refresh(context, inserted):

    base = context["base"]

    before = context["snapshot"]()

    record = context["changed"](
        collected_at=base.collected_at + timedelta(hours=1),
        raw_payload={"updated_evidence": True},
    )

    run_id = context["start_run"]()

    result = context["repository"].ingest(record, run_id)

    current, history, observations = context["snapshot"]()

    assert result.outcome == "unchanged"
    assert result.content_version == 1
    assert current["source_listing_id"] == before[0]["source_listing_id"]
    assert current["first_seen_at"] == before[0]["first_seen_at"]
    assert current["created_at"] == before[0]["created_at"]
    assert current["last_seen_at"] == record.collected_at
    assert current["collected_at"] == record.collected_at
    assert current["last_collection_run_id"] == run_id
    assert current["raw_payload"] == record.raw_payload
    assert history == before[1]
    assert len(observations) == 2

    context["assert_ledger"](run_id, result, record)


def test_changed_content(context, inserted):

    base = context["base"]

    record = context["changed"](
        salary_min="12000",
        collected_at=base.collected_at + timedelta(hours=1),
    )

    run_id = context["start_run"]()

    result = context["repository"].ingest(record, run_id)

    current, history, observations = context["snapshot"]()

    assert result.outcome == "updated"
    assert result.content_version == 2
    assert current["salary_min"] == Decimal("12000")
    assert current["source_listing_id"] == inserted[1].source_listing_id

    assert len(history) == 2
    assert len(observations) == 2

    assert history[0]["content_hash"] != history[1]["content_hash"]

    context["assert_ledger"](run_id, result, record)


def test_a_b_a_version_history(context, inserted):

    base = context["base"]

    for index, salary in enumerate(
        ["12000", "10000"],
        start=1,
    ):

        record = context["changed"](
            salary_min=salary,
            collected_at=(
                base.collected_at + timedelta(hours=index)
            ),
            raw_payload={"observation": index + 1},
        )

        result = context["repository"].ingest(
            record,
            context["start_run"](),
        )

        assert result.outcome == "updated"
        assert result.content_version == index + 1

    current, history, observations = context["snapshot"]()

    assert current["content_version"] == 3

    assert [row["content_version"] for row in history] == [
        1, 2, 3
    ]

    assert history[0]["content_hash"] == history[2]["content_hash"]
    assert history[0]["content_hash"] != history[1]["content_hash"]

    assert len(observations) == 3

    for row in history:

        record = Opportunity.model_validate(
            row["standardized_payload"]
        )

        assert generate_content_hash(record) == row["content_hash"]
        assert record.collected_at == row["observed_at"]
        assert row["contract_version"] == "3.0.0"

    assert history[0]["standardized_payload"]["raw_payload"] == base.raw_payload

    assert history[1]["standardized_payload"]["raw_payload"] == {
        "observation": 2
    }

    assert history[2]["standardized_payload"]["raw_payload"] == {
        "observation": 3
    }


def test_duplicate_retry(context, inserted):

    run_id, original = inserted

    before = context["snapshot"]()

    result = context["repository"].ingest(
        context["base"],
        run_id,
    )

    assert result.outcome == "duplicate"
    assert result.original_outcome == "inserted"
    assert result.source_listing_id == original.source_listing_id

    context["assert_preserved"](before)


def test_same_run_conflict(context, inserted):

    run_id, _ = inserted

    before = context["snapshot"]()

    result = context["repository"].ingest(
        context["changed"](title="Different title"),
        run_id,
    )

    assert result.outcome == "conflicted"
    assert result.original_outcome == "inserted"
    assert result.reason == "same_run_observation_mismatch"

    context["assert_preserved"](before)


def test_stale_observation(context, inserted):

    before = context["snapshot"]()

    record = context["changed"](
        title="Older title",
        collected_at=(
            context["base"].collected_at - timedelta(hours=1)
        ),
    )

    run_id = context["start_run"]()

    result = context["repository"].ingest(record, run_id)

    assert result.outcome == "stale"
    assert result.reason == "older_observation"

    context["assert_preserved"](before, additional=1)
    context["assert_ledger"](run_id, result, record)


def test_equal_timestamp_conflict(context, inserted):

    before = context["snapshot"]()

    record = context["changed"](title="Different title")

    run_id = context["start_run"]()

    result = context["repository"].ingest(record, run_id)

    assert result.outcome == "conflicted"
    assert result.reason == "equal_timestamp_content_mismatch"

    context["assert_preserved"](before, additional=1)
    context["assert_ledger"](run_id, result, record)


def test_equal_timestamp_same_content(context, inserted):

    before = context["snapshot"]()

    record = context["changed"](
        raw_payload={"different_evidence": True},
    )

    run_id = context["start_run"]()

    result = context["repository"].ingest(record, run_id)

    assert result.outcome == "unchanged"
    assert result.reason == "equal_timestamp_same_content"

    context["assert_preserved"](before, additional=1)
    context["assert_ledger"](run_id, result, record)


def test_retry_after_newer_update(context, inserted):

    first_run, _ = inserted

    record = context["changed"](
        title="Senior Data Engineer",
        collected_at=(
            context["base"].collected_at + timedelta(hours=1)
        ),
    )

    context["repository"].ingest(
        record,
        context["start_run"](),
    )

    before = context["snapshot"]()

    result = context["repository"].ingest(
        context["base"],
        first_run,
    )

    assert result.outcome == "duplicate"
    assert result.original_outcome == "inserted"

    context["assert_preserved"](before)


def test_finalized_run_duplicate(context, inserted):

    run_id, _ = inserted

    context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        counters=RunCounters(received=1, inserted=1),
    )

    before = context["snapshot"]()

    result = context["repository"].ingest(
        context["base"],
        run_id,
    )

    assert result.outcome == "duplicate"

    context["assert_preserved"](before)


def test_finalized_run_rejects_new_listing(context, inserted):

    run_id, _ = inserted

    context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        counters=RunCounters(received=1, inserted=1),
    )

    before = context["snapshot"]()

    identifier = uuid4().hex

    record = context["changed"](
        source_opportunity_id=identifier,
        source_url=f"https://wuzzuf.net/jobs/p/{identifier}",
    )

    with pytest.raises(CollectionRunError):

        context["repository"].ingest(record, run_id)

    context["assert_preserved"](before)

    with context["storage"].transaction(read_only=True) as conn:

        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM bronze.source_listings
            WHERE source_name = 'wuzzuf'
              AND source_identity_key = %s
            """,
            (f"id:{identifier}",),
        ).fetchone()

        assert row["total"] == 0


def test_source_mismatch(context, inserted):

    before = context["snapshot"]()

    with pytest.raises(CollectionRunError):

        context["repository"].ingest(
            context["base"],
            context["start_run"]("bayt"),
        )

    context["assert_preserved"](before)


def test_missing_run(context):

    with pytest.raises(CollectionRunError):

        context["repository"].ingest(
            context["base"],
            uuid4(),
        )

    assert context["snapshot"]() == (None, [], [])


def test_missing_source_identity(context):

    record = context["changed"](
        source_opportunity_id=None,
    )

    with pytest.raises(SourceIdentityError):

        context["repository"].ingest(
            record,
            context["start_run"](),
        )

    assert context["snapshot"]() == (None, [], [])



def get_rejections(context, run_id):

    with context["storage"].transaction(read_only=True) as conn:

        return conn.execute(
            """
            SELECT *
            FROM bronze.invalid_records
            WHERE collection_run_id = %s
            ORDER BY invalid_record_id
            """,
            (run_id,),
        ).fetchall()


def test_same_run_conflict_persistence(context, inserted):

    run_id, original = inserted

    before = context["snapshot"]()

    record = context["changed"](
        title="Conflicting title",
    )

    result = context["repository"].ingest(
        record,
        run_id,
    )

    assert result.outcome == "conflicted"

    rows = get_rejections(context, run_id)

    assert len(rows) == 1

    row = rows[0]

    assert row["failure_stage"] == "ingestion"

    assert row["error_code"] == (
        "SameRunObservationMismatch"
    )

    assert row["error_details"]["source_listing_id"] == str(
        original.source_listing_id
    )

    assert row["error_details"]["previous_observation_hash"] == (
        original.observation_hash
    )

    assert row["record_payload"] == {
        "incoming_observation_hash":
            generate_observation_hash(record),

        "incoming_content_hash":
            generate_content_hash(record),
    }

    context["assert_preserved"](before)


def test_equal_timestamp_conflict_persistence(
    context,
    inserted,
):

    run_id = context["start_run"]()

    record = context["changed"](
        title="Equal timestamp conflict",
    )

    before = context["snapshot"]()

    result = context["repository"].ingest(
        record,
        run_id,
    )

    assert result.outcome == "conflicted"

    rows = get_rejections(context, run_id)

    assert len(rows) == 1

    assert rows[0]["error_code"] == (
        "EqualTimestampContentMismatch"
    )

    context["assert_preserved"](
        before,
        additional=1,
    )

    context["assert_ledger"](
        run_id,
        result,
        record,
    )


def test_conflict_retry_does_not_duplicate_rejection(
    context,
    inserted,
):

    run_id, _ = inserted

    record = context["changed"](
        title="Repeated conflict",
    )

    repository = context["repository"]

    first = repository.ingest(record, run_id)

    assert first.outcome == "conflicted"

    before = get_rejections(context, run_id)

    assert len(before) == 1

    second = repository.ingest(record, run_id)

    assert second.outcome == "conflicted"

    assert get_rejections(context, run_id) == before


def test_stale_observation_is_not_invalid(
    context,
    inserted,
):

    run_id = context["start_run"]()

    record = context["changed"](
        collected_at=(
            context["base"].collected_at
            - timedelta(hours=1)
        ),
    )

    result = context["repository"].ingest(
        record,
        run_id,
    )

    assert result.outcome == "stale"

    assert get_rejections(context, run_id) == []


def test_conflict_rejection_and_ledger_rollback(
    context,
    inserted,
    monkeypatch,
):

    repository = context["repository"]

    run_id = context["start_run"]()

    record = context["changed"](
        title="Rollback conflict",
    )

    before = context["snapshot"]()

    class ForcedFailure(Exception):
        pass

    def fail_observation(*args, **kwargs):
        raise ForcedFailure("Synthetic ledger failure")

    monkeypatch.setattr(
        repository,
        "_insert_observation",
        fail_observation,
    )

    with pytest.raises(ForcedFailure):

        repository.ingest(record, run_id)

    context["assert_preserved"](before)

    assert get_rejections(context, run_id) == []


def test_finalized_run_rejects_new_conflict(
    context,
    inserted,
):

    run_id, _ = inserted

    context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        counters=RunCounters(
            received=1,
            inserted=1,
        ),
    )

    before = context["snapshot"]()

    record = context["changed"](
        title="New conflict after finalization",
    )

    with pytest.raises(CollectionRunError):

        context["repository"].ingest(
            record,
            run_id,
        )

    context["assert_preserved"](before)

    assert get_rejections(context, run_id) == []
