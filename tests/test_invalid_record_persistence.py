import os

from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.collection_runs import (
    CollectionRunManager,
    CollectionRunError,
    RunCounters,
)

from scrapers.storage.invalid_records import (
    InvalidRecordRepository,
)

from scrapers.utils.invalid_records import InvalidRecord


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
    repository = InvalidRecordRepository(storage)

    run_ids = []

    def start_run():

        run_id = uuid4()

        run_ids.append(run_id)

        manager.start_run(
            run_id=run_id,
            source_name="wuzzuf",
            collection_mode="api",
            collection_scope="pytest_invalid_records",
        )

        return run_id

    run_id = start_run()

    arguments = {
        "run_id": run_id,
        "source_name": "wuzzuf",
        "source_opportunity_id": "TEST123",
        "source_url": "https://wuzzuf.net/jobs/p/TEST123",
        "failure_stage": "validation",
        "error_code": "MissingTitle",
        "error_message": "Required title is missing",
        "error_details": {"field": "title"},
        "record_payload": {
            "id": "TEST123",
            "title": None,
        },
        "observed_at": datetime.now(timezone.utc),
    }

    def record(**updates):

        return repository.record(
            **{**arguments, **updates}
        )

    def rows(connection=None):

        query = """
            SELECT *
            FROM bronze.invalid_records
            WHERE collection_run_id = %s
            ORDER BY invalid_record_id
        """

        if connection is not None:

            return connection.execute(
                query,
                (run_id,),
            ).fetchall()

        with storage.transaction(read_only=True) as conn:

            return conn.execute(
                query,
                (run_id,),
            ).fetchall()

    try:

        yield {
            "storage": storage,
            "manager": manager,
            "repository": repository,
            "run_id": run_id,
            "start_run": start_run,
            "arguments": arguments,
            "record": record,
            "rows": rows,
        }

    finally:

        with storage.transaction() as conn:

            for identifier in run_ids:

                conn.execute(
                    """
                    DELETE FROM bronze.invalid_records
                    WHERE collection_run_id = %s
                    """,
                    (identifier,),
                )

                conn.execute(
                    """
                    DELETE FROM bronze.collection_runs
                    WHERE run_id = %s
                    """,
                    (identifier,),
                )


def test_insert_rejection(context):

    result = context["record"]()

    rows = context["rows"]()

    assert result.inserted is True
    assert len(result.rejection_hash) == 64
    assert len(rows) == 1

    row = rows[0]

    assert row["invalid_record_id"] == result.invalid_record_id
    assert row["rejection_hash"] == result.rejection_hash

    for field in (
        "source_opportunity_id",
        "source_url",
        "failure_stage",
        "error_code",
        "error_message",
        "error_details",
        "record_payload",
        "observed_at",
    ):

        assert row[field] == context["arguments"][field]


def test_duplicate_preserves_original(context):

    first = context["record"]()

    before = context["rows"]()

    second = context["record"](
        error_message="Different message",
        error_details={"different": True},
        observed_at=(
            context["arguments"]["observed_at"]
            + timedelta(minutes=1)
        ),
    )

    assert second.inserted is False
    assert second.invalid_record_id == first.invalid_record_id
    assert second.rejection_hash == first.rejection_hash

    assert context["rows"]() == before


def test_json_key_order_independence(context):

    first = context["record"]()

    second = context["record"](
        record_payload={
            "title": None,
            "id": "TEST123",
        },
    )

    assert second.inserted is False
    assert first.rejection_hash == second.rejection_hash


@pytest.mark.parametrize(
    "updates",
    [
        {"error_code": "DifferentError"},
        {"failure_stage": "mapping"},
        {"source_opportunity_id": "TEST456"},
        {"source_url": "https://example.com/other"},
        {"record_payload": {"different": True}},
    ],
)
def test_distinct_rejection_identity(context, updates):

    first = context["record"]()

    second = context["record"](**updates)

    assert second.inserted is True
    assert second.rejection_hash != first.rejection_hash
    assert len(context["rows"]()) == 2


def test_rejection_is_scoped_to_run(context):

    first = context["record"]()

    second = context["record"](
        run_id=context["start_run"](),
    )

    assert second.inserted is True
    assert first.rejection_hash == second.rejection_hash
    assert first.invalid_record_id != second.invalid_record_id


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [],
        ["invalid"],
        "invalid",
        42,
        False,
    ],
)
def test_supported_json_payloads(context, payload):

    result = context["record"](
        record_payload=payload,
    )

    assert result.inserted is True

    assert context["rows"]()[0]["record_payload"] == payload


def test_scraper_adapter_uses_safe_values(context):

    record = InvalidRecord(
        run_id=str(context["run_id"]),
        source_name="wuzzuf",
        source_url="https://example.com/?token=secret",
        raw_payload={"password": "secret"},
        error_type="ValidationError",
        error_message="Sensitive exception message",
    )

    result = context["repository"].record_scraper_invalid(
        record,
        failure_stage="validation",
        safe_error_message="Validation failed",
        safe_payload={"field": "title"},
    )

    assert result.inserted is True

    row = context["rows"]()[0]

    assert row["source_url"] is None
    assert row["record_payload"] == {"field": "title"}
    assert row["error_message"] == "Validation failed"
    assert row["error_code"] == "ValidationError"


def test_source_mismatch(context):

    with pytest.raises(CollectionRunError):

        context["record"](source_name="bayt")

    assert context["rows"]() == []


def test_missing_run(context):

    with pytest.raises(CollectionRunError):

        context["record"](run_id=uuid4())

    assert context["rows"]() == []


def test_finalized_run_protection(context):

    first = context["record"]()

    context["manager"].finish_run(
        run_id=context["run_id"],
        status="completed",
        counters=RunCounters(
            received=1,
            invalid=1,
        ),
    )

    before = context["rows"]()

    retry = context["record"]()

    assert retry.inserted is False
    assert retry.invalid_record_id == first.invalid_record_id

    with pytest.raises(CollectionRunError):

        context["record"](error_code="NewError")

    assert context["rows"]() == before


@pytest.mark.parametrize(
    "updates, exception",
    [
        ({"run_id": "invalid"}, TypeError),
        ({"failure_stage": "unknown"}, ValueError),
        ({"source_name": ""}, ValueError),
        ({"error_code": " "}, ValueError),
        ({"error_message": ""}, ValueError),
        ({"error_message": "bad\x00text"}, ValueError),
        ({"source_opportunity_id": ""}, ValueError),
        ({"source_url": " "}, ValueError),
        ({"error_details": []}, TypeError),
        ({"observed_at": "invalid"}, TypeError),
        ({"observed_at": datetime(2026, 1, 1)}, ValueError),
        ({"record_payload": {"value": float("nan")}}, ValueError),
        ({"record_payload": {"value": object()}}, TypeError),
    ],
)
def test_invalid_arguments(context, updates, exception):

    with pytest.raises(exception):

        context["record"](**updates)

    assert context["rows"]() == []


def test_shared_transaction_commit(context):

    with context["storage"].transaction() as conn:

        result = context["record"](connection=conn)

        assert result.inserted is True
        assert len(context["rows"](conn)) == 1
        assert context["rows"]() == []
        assert not conn.closed

    assert len(context["rows"]()) == 1


def test_shared_transaction_rollback(context):

    class ForcedFailure(Exception):
        pass

    with pytest.raises(ForcedFailure):

        with context["storage"].transaction() as conn:

            result = context["record"](connection=conn)

            assert result.inserted is True
            assert len(context["rows"](conn)) == 1

            raise ForcedFailure()

    assert context["rows"]() == []


def test_autocommit_connection_rejected(context):

    conn = context["storage"].connect()

    try:

        conn.autocommit = True

        with pytest.raises(ValueError):

            context["record"](connection=conn)

    finally:

        conn.close()

    assert context["rows"]() == []


def test_closed_connection_rejected(context):

    conn = context["storage"].connect()

    conn.close()

    with pytest.raises(ValueError):

        context["record"](connection=conn)

    assert context["rows"]() == []
