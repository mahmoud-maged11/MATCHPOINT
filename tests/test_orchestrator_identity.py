
from uuid import uuid4
from unittest.mock import Mock

import pytest

from scrapers.models import Opportunity

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

from scrapers.utils.invalid_records import (
    InvalidRecord,
)


@pytest.fixture
def orchestrator():

    instance = IngestionOrchestrator(
        Mock(),
        rejection_policy=RejectionPolicy(b"x" * 32),
    )

    instance.runs = Mock()
    instance.opportunities = Mock()
    instance.invalid_records = Mock()

    instance.runs.get_run.return_value = {
        "source_name": "wuzzuf",
        "status": "running",
    }

    return instance


def make_opportunity(identifier="ABC123"):

    return Opportunity(
        source_name="wuzzuf",
        source_opportunity_id=identifier,
        source_url="https://wuzzuf.net/jobs/p/ABC123",
        title="Synthetic Data Engineer",
        opportunity_type="job",
        raw_payload={
            "private": "synthetic-secret",
        },
    )


def make_result(opportunities=(), rejected=(), run_id=None):

    return CollectionResult(
        run_id=run_id or uuid4(),
        source_name="wuzzuf",
        opportunities=opportunities,
        invalid_records=rejected,
        status=CollectionStatus.COMPLETED,
        stop_reason=StopReason.SOURCE_EXHAUSTED,
    )


def test_valid_identity_preserved(orchestrator):

    opportunity = make_opportunity()

    result = make_result((opportunity,))

    prepared = orchestrator.prepare_collection(result)

    assert prepared.opportunities == (opportunity,)
    assert prepared.invalid_records == ()
    assert prepared.run_id == result.run_id
    assert prepared.status == result.status
    assert prepared.stop_reason == result.stop_reason


@pytest.mark.parametrize(
    "identifier",
    [None, "", " ", " ABC123", "ABC123 ", "ABC\x00"],
)
def test_invalid_identity_becomes_rejection(
    orchestrator, identifier
):

    opportunity = make_opportunity()

    opportunity = opportunity.model_copy(
        update={
            "source_opportunity_id": identifier,
        }
    )

    result = make_result((opportunity,))

    prepared = orchestrator.prepare_collection(result)

    assert prepared.accepted_count == 0
    assert prepared.rejected_count == 1

    rejected = prepared.invalid_records[0]

    assert rejected.error_type == "SourceIdentityError"
    assert rejected.run_id == str(result.run_id)
    assert rejected.source_name == result.source_name
    assert rejected.collected_at == opportunity.collected_at

    safe = orchestrator.rejection_policy.sanitize(
        rejected
    )

    assert safe.failure_stage == "identity"
    assert safe.source_opportunity_id is None
    assert safe.source_url is None

    assert "synthetic-secret" not in repr(safe)


def test_mixed_batch(orchestrator):

    valid = make_opportunity()
    invalid = make_opportunity(None)

    result = make_result((valid, invalid))

    prepared = orchestrator.prepare_collection(result)

    assert prepared.accepted_count == 1
    assert prepared.rejected_count == 1
    assert prepared.returned_count == result.returned_count


def test_existing_rejections_preserved(orchestrator):

    run_id = uuid4()

    existing = InvalidRecord(
        run_id=str(run_id),
        source_name="wuzzuf",
        raw_payload={"api_id": "123"},
        error_type="ValidationError",
        error_message="Synthetic error",
    )

    result = make_result(
        opportunities=(make_opportunity(None),),
        rejected=(existing,),
        run_id=run_id,
    )

    prepared = orchestrator.prepare_collection(result)

    assert prepared.rejected_count == 2
    assert prepared.invalid_records[0] == existing


def test_original_result_not_modified(orchestrator):

    result = make_result(
        (make_opportunity(None),)
    )

    prepared = orchestrator.prepare_collection(result)

    assert result.accepted_count == 1
    assert result.rejected_count == 0

    assert prepared.accepted_count == 0
    assert prepared.rejected_count == 1


def test_distinct_identity_rejections(orchestrator):

    first = make_opportunity(None)

    second = first.model_copy(
        update={"title": "Different opportunity"}
    )

    prepared = orchestrator.prepare_collection(
        make_result((first, second))
    )

    fingerprints = {
        orchestrator.rejection_policy.fingerprint(record)
        for record in prepared.invalid_records
    }

    assert len(fingerprints) == 2


def test_duplicate_identity_rejections(orchestrator):

    opportunity = make_opportunity(None)

    prepared = orchestrator.prepare_collection(
        make_result(
            (
                opportunity,
                opportunity.model_copy(deep=True),
            )
        )
    )

    fingerprints = {
        orchestrator.rejection_policy.fingerprint(record)
        for record in prepared.invalid_records
    }

    assert len(fingerprints) == 1


def test_missing_policy_fails_closed(orchestrator):

    orchestrator.rejection_policy = None

    with pytest.raises(RuntimeError):

        orchestrator.prepare_collection(
            make_result((make_opportunity(None),))
        )


def test_empty_collection(orchestrator):

    result = make_result()

    prepared = orchestrator.prepare_collection(result)

    assert prepared.returned_count == 0


def test_invalid_result_type(orchestrator):

    with pytest.raises(TypeError):

        orchestrator.prepare_collection({})


def test_finalized_run_rejected(orchestrator):

    orchestrator.runs.get_run.return_value = {
        "source_name": "wuzzuf",
        "status": "completed",
    }

    with pytest.raises(ValueError):

        orchestrator.prepare_collection(
            make_result((make_opportunity(),))
        )


def test_mutated_source_rejected(orchestrator):

    opportunity = make_opportunity()

    result = make_result((opportunity,))

    opportunity.source_name = "bayt"

    with pytest.raises(ValueError):

        orchestrator.prepare_collection(result)


def test_preparation_does_not_write(orchestrator):

    orchestrator.prepare_collection(
        make_result(
            (
                make_opportunity(),
                make_opportunity(None),
            )
        )
    )

    orchestrator.opportunities.ingest.assert_not_called()
    orchestrator.invalid_records.record.assert_not_called()
    orchestrator.runs.finish_run.assert_not_called()
