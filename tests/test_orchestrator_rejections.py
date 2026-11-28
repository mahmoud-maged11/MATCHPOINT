
from uuid import uuid4
from unittest.mock import Mock

import pytest

from scrapers.collection_result import (
    CollectionResult,
    CollectionStatus,
    StopReason,
)

from scrapers.storage.orchestrator import (
    IngestionOrchestrator,
)

from scrapers.storage.rejection_policy import (
    RejectionPolicy,
)

from scrapers.storage.invalid_records import (
    RejectionResult,
)

from scrapers.utils.invalid_records import (
    InvalidRecord,
)


@pytest.fixture
def run_id():

    return uuid4()


@pytest.fixture
def policy():

    return RejectionPolicy(b"x" * 32)


@pytest.fixture
def orchestrator(policy):

    instance = IngestionOrchestrator(
        Mock(),
        rejection_policy=policy,
    )

    instance.runs = Mock()
    instance.invalid_records = Mock()
    instance.opportunities = Mock()

    instance.runs.get_run.return_value = {
        "source_name": "wuzzuf",
        "status": "running",
    }

    instance.invalid_records.record.return_value = (
        RejectionResult(
            invalid_record_id=uuid4(),
            rejection_hash="a" * 64,
            inserted=True,
        )
    )

    return instance


def make_record(run_id, payload=None):

    return InvalidRecord(
        run_id=str(run_id),
        source_name="wuzzuf",
        source_url=(
            "https://example.com/job"
            "?token=synthetic-secret"
        ),
        raw_payload=(
            payload
            if payload is not None
            else {
                "api_id": "ABC123",
                "email": "synthetic@example.com",
                "token": "synthetic-secret",
            }
        ),
        error_type="ValidationError",
        error_message="Private synthetic-secret",
    )


def make_result(run_id, records=()):

    return CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        invalid_records=records,
        status=CollectionStatus.COMPLETED,
        stop_reason=StopReason.SOURCE_EXHAUSTED,
    )


def test_persist_rejected(
    orchestrator, run_id
):

    record = make_record(run_id)

    result = orchestrator.persist_rejected(
        make_result(run_id, (record,))
    )

    assert result.received == 1
    assert result.processed == 1
    assert result.inserted == 1
    assert result.duplicate_inputs == 0
    assert result.previously_persisted == 0


def test_only_sanitized_data_reaches_repository(
    orchestrator, run_id
):

    record = make_record(run_id)

    orchestrator.persist_rejected(
        make_result(run_id, (record,))
    )

    kwargs = (
        orchestrator.invalid_records.record
        .call_args.kwargs
    )

    assert kwargs["run_id"] == run_id
    assert kwargs["source_name"] == "wuzzuf"
    assert kwargs["source_opportunity_id"] == "ABC123"
    assert kwargs["source_url"] is None
    assert kwargs["failure_stage"] == "validation"
    assert kwargs["error_code"] == "ValidationError"
    assert kwargs["observed_at"] == record.collected_at

    assert "synthetic-secret" not in repr(kwargs)
    assert "synthetic@example.com" not in repr(kwargs)

    assert set(kwargs["record_payload"]) == {
        "api_id",
        "policy_version",
        "evidence_fingerprint",
    }


def test_empty_rejected_batch(
    orchestrator, run_id
):

    result = orchestrator.persist_rejected(
        make_result(run_id)
    )

    assert result.received == 0
    assert result.processed == 0
    assert result.inserted == 0

    orchestrator.invalid_records.record.assert_not_called()


def test_duplicate_rejected_inputs(
    orchestrator, run_id
):

    record = make_record(run_id)

    result = orchestrator.persist_rejected(
        make_result(
            run_id,
            (
                record,
                record.model_copy(deep=True),
            ),
        )
    )

    assert result.received == 1
    assert result.duplicate_inputs == 1
    assert result.processed == 1

    orchestrator.invalid_records.record.assert_called_once()


def test_distinct_rejected_evidence_preserved(
    orchestrator, run_id
):

    first = make_record(
        run_id,
        {"card_html": "<p>First</p>"},
    )

    second = make_record(
        run_id,
        {"card_html": "<p>Second</p>"},
    )

    result = orchestrator.persist_rejected(
        make_result(run_id, (first, second))
    )

    assert result.received == 2
    assert result.duplicate_inputs == 0

    calls = (
        orchestrator.invalid_records.record
        .call_args_list
    )

    assert len(calls) == 2

    fingerprints = {
        call.kwargs["record_payload"][
            "evidence_fingerprint"
        ]
        for call in calls
    }

    assert len(fingerprints) == 2


def test_previously_persisted_rejection(
    orchestrator, run_id
):

    orchestrator.invalid_records.record.return_value = (
        RejectionResult(
            invalid_record_id=uuid4(),
            rejection_hash="b" * 64,
            inserted=False,
        )
    )

    result = orchestrator.persist_rejected(
        make_result(
            run_id,
            (make_record(run_id),),
        )
    )

    assert result.received == 1
    assert result.processed == 1
    assert result.inserted == 0
    assert result.previously_persisted == 1


def test_missing_policy_fails_closed(
    orchestrator, run_id
):

    orchestrator.rejection_policy = None

    with pytest.raises(
        RuntimeError,
        match="Rejection policy is required",
    ):

        orchestrator.persist_rejected(
            make_result(
                run_id,
                (make_record(run_id),),
            )
        )

    orchestrator.invalid_records.record.assert_not_called()


def test_empty_batch_without_policy(
    orchestrator, run_id
):

    orchestrator.rejection_policy = None

    result = orchestrator.persist_rejected(
        make_result(run_id)
    )

    assert result.received == 0


def test_invalid_policy_type():

    with pytest.raises(TypeError):

        IngestionOrchestrator(
            Mock(),
            rejection_policy="invalid",
        )


@pytest.mark.parametrize(
    "run",
    [
        None,
        {
            "source_name": "bayt",
            "status": "running",
        },
        {
            "source_name": "wuzzuf",
            "status": "completed",
        },
    ],
)
def test_invalid_run_prevents_rejection_persistence(
    orchestrator, run_id, run
):

    orchestrator.runs.get_run.return_value = run

    with pytest.raises(ValueError):

        orchestrator.persist_rejected(
            make_result(
                run_id,
                (make_record(run_id),),
            )
        )

    orchestrator.invalid_records.record.assert_not_called()


def test_partial_collection_rejections(
    orchestrator, run_id
):

    result = CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        invalid_records=(make_record(run_id),),
        status=CollectionStatus.PARTIAL,
        stop_reason=StopReason.SOURCE_ERROR,
    )

    persisted = orchestrator.persist_rejected(
        result
    )

    assert persisted.received == 1
    assert persisted.inserted == 1


def test_failed_collection_rejections(
    orchestrator, run_id
):

    result = CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        invalid_records=(make_record(run_id),),
        status=CollectionStatus.FAILED,
        stop_reason=StopReason.PARSING_ERROR,
    )

    persisted = orchestrator.persist_rejected(
        result
    )

    assert persisted.received == 1


def test_storage_error_propagates(
    orchestrator, run_id
):

    orchestrator.invalid_records.record.side_effect = (
        RuntimeError("Storage failure")
    )

    with pytest.raises(RuntimeError):

        orchestrator.persist_rejected(
            make_result(
                run_id,
                (make_record(run_id),),
            )
        )

    orchestrator.runs.finish_run.assert_not_called()


def test_sanitization_failure_prevents_batch_writes(
    orchestrator, run_id
):

    first = make_record(run_id)

    second = make_record(
        run_id,
        {"invalid_number": float("nan")},
    )

    with pytest.raises(ValueError):

        orchestrator.persist_rejected(
            make_result(
                run_id,
                (first, second),
            )
        )

    orchestrator.invalid_records.record.assert_not_called()


def test_mutated_record_run_id_rejected(
    orchestrator, run_id
):

    record = make_record(run_id)

    result = make_result(
        run_id, (record,)
    )

    record.run_id = str(uuid4())

    with pytest.raises(ValueError):

        orchestrator.persist_rejected(result)

    orchestrator.invalid_records.record.assert_not_called()


def test_mutated_record_source_rejected(
    orchestrator, run_id
):

    record = make_record(run_id)

    result = make_result(
        run_id, (record,)
    )

    record.source_name = "bayt"

    with pytest.raises(ValueError):

        orchestrator.persist_rejected(result)

    orchestrator.invalid_records.record.assert_not_called()


def test_invalid_result_type(orchestrator):

    with pytest.raises(TypeError):

        orchestrator.persist_rejected({})


def test_persistence_does_not_finalize_run(
    orchestrator, run_id
):

    orchestrator.persist_rejected(
        make_result(
            run_id,
            (make_record(run_id),),
        )
    )

    orchestrator.runs.finish_run.assert_not_called()
    orchestrator.opportunities.ingest.assert_not_called()
