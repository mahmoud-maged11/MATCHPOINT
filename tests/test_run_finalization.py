import os

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

    run_id = uuid4()
    identifier = uuid4().hex

    manager.start_run(
        run_id=run_id,
        source_name="wuzzuf",
        collection_mode="api",
        collection_scope="pytest_finalization",
    )

    opportunity = Opportunity(
        source_name="wuzzuf",
        source_opportunity_id=identifier,
        source_url=(
            f"https://wuzzuf.net/jobs/p/{identifier}"
        ),
        title="Data Engineer",
        opportunity_type="job",
        raw_payload={"id": identifier},
    )

    def insert():

        result = repository.ingest(
            opportunity,
            run_id,
        )

        assert result.outcome == "inserted"

        return result

    def reject():

        return invalid.record(
            run_id=run_id,
            source_name="wuzzuf",
            failure_stage="validation",
            error_code="MissingTitle",
            error_message="Required title is missing",
            record_payload={"title": None},
        )

    def finish(**arguments):

        return manager.finish_run(
            run_id=run_id,
            **arguments,
        )

    def get_run():

        return manager.get_run(run_id)

    try:

        yield {
            "storage": storage,
            "manager": manager,
            "repository": repository,
            "run_id": run_id,
            "opportunity": opportunity,
            "insert": insert,
            "reject": reject,
            "finish": finish,
            "get_run": get_run,
        }

    finally:

        with storage.transaction() as conn:

            for table in (
                "invalid_records",
                "ingestion_observations",
                "source_listing_history",
            ):

                from psycopg import sql

                conn.execute(
                    sql.SQL(
                        """
                        DELETE FROM bronze.{}
                        WHERE collection_run_id = %s
                        """
                    ).format(sql.Identifier(table)),
                    (run_id,),
                )

            conn.execute(
                """
                DELETE FROM bronze.source_listings
                WHERE last_collection_run_id = %s
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


def test_automatic_finalization(context):

    context["insert"]()
    context["reject"]()

    result = context["finish"](
        status="completed",
        received=2,
    )

    assert result["status"] == "completed"
    assert result["records_received"] == 2
    assert result["records_inserted"] == 1
    assert result["records_invalid"] == 1
    assert result["records_updated"] == 0
    assert result["records_unchanged"] == 0
    assert result["records_stale"] == 0
    assert result["records_conflicted"] == 0

    assert result["finished_at"] is not None

    assert context["get_run"]() == result


def test_empty_run_finalization(context):

    result = context["finish"](
        status="completed",
        received=0,
    )

    assert result["status"] == "completed"
    assert result["records_received"] == 0
    assert result["records_inserted"] == 0


def test_matching_manual_counters(context):

    context["insert"]()

    result = context["finish"](
        status="completed",
        counters=RunCounters(
            received=1,
            inserted=1,
        ),
    )

    assert result["records_inserted"] == 1
    assert result["status"] == "completed"


def test_incorrect_manual_counters(context):

    context["insert"]()

    before = context["get_run"]()

    with pytest.raises(CollectionRunError):

        context["finish"](
            status="completed",
            counters=RunCounters(
                received=1,
                updated=1,
            ),
        )

    assert context["get_run"]() == before


def test_fake_inserted_counter_rejected(context):

    before = context["get_run"]()

    with pytest.raises(CollectionRunError):

        context["finish"](
            status="completed",
            counters=RunCounters(
                received=1,
                inserted=1,
            ),
        )

    assert context["get_run"]() == before


def test_completed_run_with_unprocessed_records(context):

    context["insert"]()

    before = context["get_run"]()

    with pytest.raises(ValueError):

        context["finish"](
            status="completed",
            received=3,
        )

    assert context["get_run"]() == before


def test_underreported_received(context):

    context["insert"]()

    before = context["get_run"]()

    with pytest.raises(CollectionRunError):

        context["finish"](
            status="completed",
            received=0,
        )

    assert context["get_run"]() == before


@pytest.mark.parametrize(
    "status",
    ["partial", "failed", "aborted"],
)
def test_unsuccessful_run_preserves_processed_counts(
    context,
    status,
):

    context["insert"]()

    result = context["finish"](
        status=status,
        received=3,
        error_message="Synthetic interruption",
    )

    assert result["status"] == status
    assert result["records_received"] == 3
    assert result["records_inserted"] == 1
    assert result["finished_at"] is not None

    assert result["error_message"] == (
        "Synthetic interruption"
    )


def test_retry_does_not_inflate_final_counters(context):

    context["insert"]()

    duplicate = context["repository"].ingest(
        context["opportunity"],
        context["run_id"],
    )

    assert duplicate.outcome == "duplicate"

    result = context["finish"](
        status="completed",
        received=1,
    )

    assert result["records_inserted"] == 1
    assert result["records_received"] == 1


def test_conflict_counted_once(context):

    context["insert"]()

    record = Opportunity.model_validate({
        **context["opportunity"].model_dump(mode="json"),
        "title": "Conflicting title",
    })

    result = context["repository"].ingest(
        record,
        context["run_id"],
    )

    assert result.outcome == "conflicted"

    result = context["finish"](
        status="completed",
        received=2,
    )

    assert result["records_inserted"] == 1
    assert result["records_conflicted"] == 1
    assert result["records_invalid"] == 0


def test_reconciliation_failure_preserves_run(
    context,
    monkeypatch,
):

    context["insert"]()

    before = context["get_run"]()

    class ForcedFailure(Exception):
        pass

    def fail(*args, **kwargs):

        raise ForcedFailure(
            "Synthetic reconciliation failure"
        )

    monkeypatch.setattr(
        RunCounterRepository,
        "calculate",
        staticmethod(fail),
    )

    with pytest.raises(ForcedFailure):

        context["finish"](
            status="completed",
            received=1,
        )

    assert context["get_run"]() == before


def test_duplicate_finalization_rejected(context):

    context["insert"]()

    first = context["finish"](
        status="completed",
        received=1,
    )

    with pytest.raises(CollectionRunError):

        context["finish"](
            status="completed",
            received=1,
        )

    assert context["get_run"]() == first


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"received": -1},
        {"received": True},
        {"received": 1.5},
        {
            "received": 0,
            "counters": RunCounters(),
        },
    ],
)
def test_invalid_finalization_arguments(
    context,
    arguments,
):

    before = context["get_run"]()

    with pytest.raises(ValueError):

        context["finish"](
            status="completed",
            **arguments,
        )

    assert context["get_run"]() == before
