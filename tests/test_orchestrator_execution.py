
from uuid import uuid4
from unittest.mock import Mock

import pytest

from scrapers.base_scraper import BaseScraper

from scrapers.collection_result import (
    CollectionResult,
    CollectionStatus,
    StopReason,
)

from scrapers.models import Opportunity

from scrapers.storage.orchestrator import (
    IngestionOrchestrator,
    IngestionExecutionError,
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
def orchestrator(run_id):

    instance = IngestionOrchestrator(
        Mock(),
        rejection_policy=RejectionPolicy(b"x" * 32),
    )

    instance.runs = Mock()
    instance.opportunities = Mock()
    instance.invalid_records = Mock()

    instance.runs.start_run.return_value = run_id

    instance.runs.get_run.return_value = {
        "source_name": "wuzzuf",
        "status": "running",
    }

    instance.runs.finish_run.side_effect = (
        lambda **kwargs: kwargs
    )

    instance.invalid_records.record.return_value = (
        RejectionResult(
            invalid_record_id=uuid4(),
            rejection_hash="a" * 64,
            inserted=True,
        )
    )

    return instance


@pytest.fixture
def opportunity():

    return Opportunity(
        source_name="wuzzuf",
        source_opportunity_id="ABC123",
        source_url="https://wuzzuf.net/jobs/p/ABC123",
        title="Synthetic Data Engineer",
        opportunity_type="job",
        raw_payload={"id": "ABC123"},
    )


def make_result(
    run_id,
    opportunities=(),
    rejected=(),
    status=CollectionStatus.COMPLETED,
    reason=StopReason.SOURCE_EXHAUSTED,
):

    return CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        opportunities=opportunities,
        invalid_records=rejected,
        status=status,
        stop_reason=reason,
    )


def make_rejection(run_id):

    return InvalidRecord(
        run_id=str(run_id),
        source_name="wuzzuf",
        raw_payload={"api_id": "XYZ123"},
        error_type="ValidationError",
        error_message="Synthetic error",
    )


def make_scraper(result):

    scraper = Mock(spec=BaseScraper)

    scraper.source_name = "wuzzuf"
    scraper.last_result = result
    scraper.run_with_result.return_value = result

    return scraper


def test_complete_execution(
    orchestrator, run_id, opportunity
):

    result = make_result(
        run_id,
        (opportunity,),
        (make_rejection(run_id),),
    )

    scraper = make_scraper(result)

    executed = orchestrator.execute(
        scraper=scraper,
        collection_mode="api",
        run_id=run_id,
    )

    assert executed.run_id == run_id
    assert executed.received == 2
    assert executed.collection_status == (
        CollectionStatus.COMPLETED
    )

    scraper.run_with_result.assert_called_once_with(
        run_id=run_id
    )

    orchestrator.runs.finish_run.assert_called_once_with(
        run_id=run_id,
        status="completed",
        received=2,
        error_message=None,
    )


def test_generated_run_id(
    orchestrator, run_id, monkeypatch
):

    monkeypatch.setattr(
        "scrapers.storage.orchestrator.uuid4",
        lambda: run_id,
    )

    result = make_result(run_id)

    executed = orchestrator.execute(
        scraper=make_scraper(result),
        collection_mode="api",
    )

    assert executed.run_id == run_id

    assert (
        orchestrator.runs.start_run.call_args
        .kwargs["run_id"]
        == run_id
    )


def test_empty_completed_collection(
    orchestrator, run_id
):

    executed = orchestrator.persist_collection(
        make_result(run_id)
    )

    assert executed.received == 0

    orchestrator.runs.finish_run.assert_called_once_with(
        run_id=run_id,
        status="completed",
        received=0,
        error_message=None,
    )


@pytest.mark.parametrize(
    "status,reason",
    [
        (
            CollectionStatus.PARTIAL,
            StopReason.SOURCE_ERROR,
        ),
        (
            CollectionStatus.FAILED,
            StopReason.PARSING_ERROR,
        ),
        (
            CollectionStatus.ABORTED,
            StopReason.INTERRUPTED,
        ),
    ],
)
def test_unsuccessful_collection_finalization(
    orchestrator, run_id, status, reason
):

    executed = orchestrator.persist_collection(
        make_result(
            run_id,
            rejected=(make_rejection(run_id),),
            status=status,
            reason=reason,
        )
    )

    assert executed.received == 1

    orchestrator.runs.finish_run.assert_called_once_with(
        run_id=run_id,
        status=status.value,
        received=1,
        error_message=(
            f"Collection stopped: {reason.value}"
        ),
    )


def test_duplicate_inputs_excluded(
    orchestrator, run_id, opportunity
):

    rejected = make_rejection(run_id)

    executed = orchestrator.persist_collection(
        make_result(
            run_id,
            (
                opportunity,
                opportunity.model_copy(deep=True),
            ),
            (
                rejected,
                rejected.model_copy(deep=True),
            ),
        )
    )

    assert executed.received == 2
    assert executed.duplicate_inputs == 2

    assert (
        orchestrator.runs.finish_run.call_args
        .kwargs["received"]
        == 2
    )


def test_identity_rejection_counted(
    orchestrator, run_id, opportunity
):

    invalid = opportunity.model_copy(
        update={"source_opportunity_id": None}
    )

    executed = orchestrator.persist_collection(
        make_result(
            run_id,
            (opportunity, invalid),
        )
    )

    assert executed.received == 2
    assert executed.accepted.received == 1
    assert executed.rejected.received == 1

    orchestrator.opportunities.ingest.assert_called_once()

    assert (
        orchestrator.invalid_records.record.call_args
        .kwargs["failure_stage"]
        == "identity"
    )


def test_distinct_conflict_inputs_preserved(
    orchestrator, run_id, opportunity
):

    changed = opportunity.model_copy(
        update={"title": "Different title"}
    )

    executed = orchestrator.persist_collection(
        make_result(
            run_id,
            (opportunity, changed),
        )
    )

    assert executed.received == 2

    assert (
        orchestrator.opportunities.ingest.call_count
        == 2
    )


def test_retry_outcome_does_not_reduce_received(
    orchestrator, run_id, opportunity
):

    outcome = Mock()
    outcome.outcome = "duplicate"
    outcome.original_outcome = "inserted"

    orchestrator.opportunities.ingest.return_value = (
        outcome
    )

    executed = orchestrator.persist_collection(
        make_result(run_id, (opportunity,))
    )

    assert executed.received == 1

    assert (
        orchestrator.runs.finish_run.call_args
        .kwargs["received"]
        == 1
    )


def test_accepted_storage_failure_preserves_result(
    orchestrator, run_id, opportunity
):

    result = make_result(run_id, (opportunity,))

    orchestrator.opportunities.ingest.side_effect = (
        RuntimeError("Synthetic storage failure")
    )

    with pytest.raises(IngestionExecutionError) as caught:

        orchestrator.persist_collection(result)

    assert caught.value.run_id == run_id
    assert caught.value.stage == "accepted_persistence"
    assert caught.value.collection_result is result

    orchestrator.runs.finish_run.assert_not_called()


def test_rejected_storage_failure(
    orchestrator, run_id, opportunity
):

    result = make_result(
        run_id,
        (opportunity,),
        (make_rejection(run_id),),
    )

    orchestrator.invalid_records.record.side_effect = (
        RuntimeError("Synthetic storage failure")
    )

    with pytest.raises(IngestionExecutionError) as caught:

        orchestrator.persist_collection(result)

    assert caught.value.stage == "rejected_persistence"
    assert caught.value.collection_result is result

    orchestrator.opportunities.ingest.assert_called_once()
    orchestrator.runs.finish_run.assert_not_called()


def test_finalization_failure_preserves_result(
    orchestrator, run_id, opportunity
):

    result = make_result(run_id, (opportunity,))

    orchestrator.runs.finish_run.side_effect = (
        RuntimeError("Synthetic finalization failure")
    )

    with pytest.raises(IngestionExecutionError) as caught:

        orchestrator.persist_collection(result)

    assert caught.value.stage == "finalization"
    assert caught.value.collection_result is result

    orchestrator.runs.finish_run.assert_called_once()


def test_sanitization_preflight(
    orchestrator, run_id, opportunity
):

    rejected = make_rejection(run_id)

    rejected.raw_payload = {
        "invalid": float("nan")
    }

    result = make_result(
        run_id,
        (opportunity,),
        (rejected,),
    )

    with pytest.raises(IngestionExecutionError) as caught:

        orchestrator.persist_collection(result)

    assert caught.value.stage == "preparation"

    orchestrator.opportunities.ingest.assert_not_called()
    orchestrator.invalid_records.record.assert_not_called()
    orchestrator.runs.finish_run.assert_not_called()


def test_missing_policy_prevents_run_creation(
    orchestrator, run_id
):

    orchestrator.rejection_policy = None

    scraper = make_scraper(make_result(run_id))

    with pytest.raises(RuntimeError):

        orchestrator.execute(
            scraper=scraper,
            collection_mode="api",
            run_id=run_id,
        )

    orchestrator.runs.start_run.assert_not_called()
    scraper.run_with_result.assert_not_called()


def test_run_creation_failure(
    orchestrator, run_id
):

    orchestrator.runs.start_run.side_effect = (
        RuntimeError("Synthetic connection failure")
    )

    scraper = make_scraper(make_result(run_id))

    with pytest.raises(IngestionExecutionError) as caught:

        orchestrator.execute(
            scraper=scraper,
            collection_mode="api",
            run_id=run_id,
        )

    assert caught.value.stage == "run_creation"
    assert caught.value.run_id == run_id

    scraper.run_with_result.assert_not_called()


def test_collection_exception_finalizes_failed_result(
    orchestrator, run_id
):

    result = make_result(
        run_id,
        rejected=(make_rejection(run_id),),
        status=CollectionStatus.FAILED,
        reason=StopReason.UNKNOWN,
    )

    scraper = make_scraper(result)

    scraper.run_with_result.side_effect = (
        RuntimeError("Synthetic collection failure")
    )

    with pytest.raises(IngestionExecutionError) as caught:

        orchestrator.execute(
            scraper=scraper,
            collection_mode="api",
            run_id=run_id,
        )

    assert caught.value.stage == "collection"

    assert (
        orchestrator.runs.finish_run.call_args
        .kwargs["status"]
        == "failed"
    )

    orchestrator.invalid_records.record.assert_called_once()


def test_interruption_finalizes_aborted_result(
    orchestrator, run_id
):

    result = make_result(
        run_id,
        status=CollectionStatus.ABORTED,
        reason=StopReason.INTERRUPTED,
    )

    scraper = make_scraper(result)

    scraper.run_with_result.side_effect = (
        KeyboardInterrupt()
    )

    with pytest.raises(KeyboardInterrupt):

        orchestrator.execute(
            scraper=scraper,
            collection_mode="api",
            run_id=run_id,
        )

    assert (
        orchestrator.runs.finish_run.call_args
        .kwargs["status"]
        == "aborted"
    )


def test_stale_last_result_not_persisted(
    orchestrator, run_id
):

    scraper = make_scraper(
        make_result(
            uuid4(),
            status=CollectionStatus.FAILED,
            reason=StopReason.UNKNOWN,
        )
    )

    scraper.run_with_result.side_effect = (
        RuntimeError("Synthetic failure")
    )

    with pytest.raises(IngestionExecutionError) as caught:

        orchestrator.execute(
            scraper=scraper,
            collection_mode="api",
            run_id=run_id,
        )

    assert caught.value.collection_result is None

    orchestrator.runs.finish_run.assert_not_called()
    orchestrator.opportunities.ingest.assert_not_called()


def test_no_checkpoint_advance(
    orchestrator, run_id
):

    orchestrator.persist_collection(
        make_result(run_id)
    )

    assert (
        "checkpoint"
        not in orchestrator.runs.finish_run.call_args.kwargs
    )
