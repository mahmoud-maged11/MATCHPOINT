from uuid import uuid4

import pytest

from scrapers.storage.invalid_records import (
    InvalidRecordRepository,
)

from scrapers.storage.orchestrator import (
    IngestionExecutionError,
)

from test_incremental_pipeline import (
    pipeline,
    make_scraper,
    execute,
    pytestmark,
)


def mark_deferred(scraper):

    original = scraper.fetch_company_name

    def unavailable(company_id):

        if company_id is not None:
            scraper.company_access_failures.add(
                str(company_id).strip()
            )

        return None

    scraper.fetch_company_name = unavailable

    return scraper


def test_rejection_inside_protected_transaction(
    pipeline,
):

    orchestrator = pipeline["orchestrator"]
    storage = orchestrator.storage
    run_id = pipeline["run_id"]

    orchestrator.runs.start_run(
        source_name="egyincs",
        collection_mode="api",
        collection_scope="jobs",
        run_id=run_id,
    )

    repository = InvalidRecordRepository(storage)

    with storage.connect() as conn:

        conn.autocommit = True

        with conn.transaction():

            kwargs = {
                "connection": conn,
                "run_id": run_id,
                "source_name": "egyincs",
                "source_opportunity_id": "12345",
                "failure_stage": "mapping",
                "error_code": "TestRejection",
                "error_message": "Synthetic rejection",
                "record_payload": {
                    "id": 12345,
                    "endpoint": "jobs",
                },
            }

            first = repository.record(**kwargs)
            second = repository.record(**kwargs)

            assert first.inserted
            assert not second.inserted

            assert (
                first.invalid_record_id
                == second.invalid_record_id
            )

    with storage.transaction(read_only=True) as conn:

        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM bronze.invalid_records
            WHERE collection_run_id = %s
            """,
            (run_id,),
        ).fetchone()

        assert row["n"] == 1


def test_rejection_requires_active_transaction(
    pipeline,
):

    storage = pipeline["orchestrator"].storage
    repository = InvalidRecordRepository(storage)

    with storage.connect() as conn:

        conn.autocommit = True

        with pytest.raises(
            ValueError,
            match="active transaction",
        ):

            repository.record(
                connection=conn,
                run_id=uuid4(),
                source_name="egyincs",
                failure_stage="mapping",
                error_code="TestRejection",
                error_message="Synthetic rejection",
            )


def deferred_scraper():

    from unittest.mock import Mock

    from test_egyincs_incremental import (
        record,
        response,
    )

    scraper = make_scraper()

    records = [
        {
            **record(i),
            "felan-jobs_select_company": 123,
        }
        for i in (1, 2, 3)
    ]

    scraper.fetch = Mock(
        side_effect=[
            response(records[:2], 3, 2),
            response(records[2:], 3, 2),
        ]
    )

    return mark_deferred(scraper)


def assert_deferred(pipeline, row):

    assert row["status"] == "completed"
    assert row["records_received"] == 3
    assert row["records_inserted"] == 3
    assert row["records_invalid"] == 0

    assert "checkpoint_coverage" not in row["metadata"]
    assert "checkpoint_finalization" not in row["metadata"]

    assert pipeline["checkpoint"]() is None

    storage = pipeline["orchestrator"].storage

    with storage.transaction(read_only=True) as conn:

        rows = conn.execute(
            """
            SELECT raw_payload
            FROM bronze.source_listings
            WHERE last_collection_run_id = %s
            """,
            (pipeline["run_id"],),
        ).fetchall()

    assert len(rows) == 3

    assert all(
        item["raw_payload"].get(
            "_matchpoint_company_enrichment"
        ) == "access_denied"
        for item in rows
    )


def test_deferred_enrichment_persisted(pipeline):

    result = execute(
        pipeline,
        deferred_scraper(),
    )

    assert_deferred(
        pipeline,
        result.finalized_run,
    )


def test_deferred_enrichment_recovery(
    pipeline,
    monkeypatch,
):

    orchestrator = pipeline["orchestrator"]

    def crash(*args, **kwargs):
        raise RuntimeError("Synthetic persistence failure")

    monkeypatch.setattr(
        orchestrator.opportunities,
        "ingest",
        crash,
    )

    with pytest.raises(IngestionExecutionError):

        execute(
            pipeline,
            deferred_scraper(),
        )

    recovered = pipeline["new_orchestrator"]().recover(
        run_id=pipeline["run_id"],
    )

    assert_deferred(
        pipeline,
        recovered.finalized_run,
    )

    repeated = pipeline["new_orchestrator"]().recover(
        run_id=pipeline["run_id"],
    )

    assert repeated.already_finalized

    assert repeated.finalized_run == (
        recovered.finalized_run
    )
