
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
)


@pytest.fixture
def orchestrator():

    instance = IngestionOrchestrator(Mock())

    instance.runs = Mock()
    instance.opportunities = Mock()
    instance.invalid_records = Mock()
    instance.counters = Mock()

    instance.runs.get_run.return_value = {
        "source_name": "wuzzuf",
        "status": "running",
    }

    return instance


@pytest.fixture
def scraper():

    instance = Mock(spec=BaseScraper)

    instance.source_name = "wuzzuf"

    return instance


@pytest.fixture
def run_id():

    return uuid4()


@pytest.fixture
def opportunity():

    return Opportunity(
        source_name="wuzzuf",
        source_opportunity_id="synthetic-101",
        source_url=(
            "https://wuzzuf.net/jobs/p/"
            "synthetic-101"
        ),
        title="Synthetic Data Engineer",
        opportunity_type="job",
        raw_payload={"id": "synthetic-101"},
    )


def make_result(run_id, opportunities=()):

    return CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        opportunities=opportunities,
        status=CollectionStatus.COMPLETED,
        stop_reason=StopReason.SOURCE_EXHAUSTED,
    )


def test_start_collection(
    orchestrator, scraper, run_id
):

    orchestrator.runs.start_run.return_value = (
        run_id
    )

    result = orchestrator.start_collection(
        scraper=scraper,
        collection_mode="api",
        collection_scope="default",
        metadata={"max_jobs": 5},
        run_id=run_id,
    )

    assert result == run_id

    orchestrator.runs.start_run.assert_called_once_with(
        source_name="wuzzuf",
        collection_mode="api",
        collection_scope="default",
        metadata={"max_jobs": 5},
        run_id=run_id,
    )

    scraper.run_with_result.assert_not_called()


def test_collect_reuses_run_id(
    orchestrator, scraper, run_id
):

    expected = make_result(run_id)

    scraper.run_with_result.return_value = expected

    result = orchestrator.collect(
        scraper=scraper,
        run_id=run_id,
    )

    assert result is expected

    scraper.run_with_result.assert_called_once_with(
        run_id=run_id
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
def test_invalid_run_prevents_collection(
    orchestrator, scraper, run_id, run
):

    orchestrator.runs.get_run.return_value = run

    with pytest.raises(ValueError):

        orchestrator.collect(
            scraper=scraper,
            run_id=run_id,
        )

    scraper.run_with_result.assert_not_called()


def test_invalid_run_id_type(
    orchestrator, scraper
):

    with pytest.raises(TypeError):

        orchestrator.collect(
            scraper=scraper,
            run_id="invalid",
        )

    orchestrator.runs.get_run.assert_not_called()


def test_result_run_mismatch(
    orchestrator, scraper, run_id
):

    scraper.run_with_result.return_value = (
        make_result(uuid4())
    )

    with pytest.raises(ValueError):

        orchestrator.collect(
            scraper=scraper,
            run_id=run_id,
        )


def test_result_source_mismatch(
    orchestrator, scraper, run_id
):

    scraper.run_with_result.return_value = (
        CollectionResult(
            run_id=run_id,
            source_name="bayt",
        )
    )

    with pytest.raises(ValueError):

        orchestrator.collect(
            scraper=scraper,
            run_id=run_id,
        )


def test_invalid_result_type(
    orchestrator, scraper, run_id
):

    scraper.run_with_result.return_value = []

    with pytest.raises(TypeError):

        orchestrator.collect(
            scraper=scraper,
            run_id=run_id,
        )


def test_persist_accepted(
    orchestrator, run_id, opportunity
):

    result = make_result(
        run_id, (opportunity,)
    )

    persisted = orchestrator.persist_accepted(
        result
    )

    assert persisted.received == 1
    assert persisted.processed == 1
    assert persisted.duplicate_inputs == 0

    orchestrator.opportunities.ingest.assert_called_once_with(
        opportunity, run_id
    )


def test_empty_result(
    orchestrator, run_id
):

    persisted = orchestrator.persist_accepted(
        make_result(run_id)
    )

    assert persisted.received == 0
    assert persisted.processed == 0
    assert persisted.duplicate_inputs == 0

    orchestrator.opportunities.ingest.assert_not_called()


def test_exact_duplicate_inputs(
    orchestrator, run_id, opportunity
):

    result = make_result(
        run_id,
        (
            opportunity,
            opportunity.model_copy(deep=True),
        ),
    )

    persisted = orchestrator.persist_accepted(
        result
    )

    assert persisted.received == 1
    assert persisted.processed == 1
    assert persisted.duplicate_inputs == 1

    orchestrator.opportunities.ingest.assert_called_once()


def test_distinct_observations_are_preserved(
    orchestrator, run_id, opportunity
):

    changed = opportunity.model_copy(
        update={"title": "Updated title"}
    )

    result = make_result(
        run_id,
        (opportunity, changed),
    )

    persisted = orchestrator.persist_accepted(
        result
    )

    assert persisted.received == 2
    assert persisted.processed == 2
    assert persisted.duplicate_inputs == 0

    assert (
        orchestrator.opportunities.ingest.call_count
        == 2
    )


def test_partial_collection_can_be_persisted(
    orchestrator, run_id, opportunity
):

    result = CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        opportunities=(opportunity,),
        status=CollectionStatus.PARTIAL,
        stop_reason=StopReason.SOURCE_ERROR,
    )

    persisted = orchestrator.persist_accepted(
        result
    )

    assert persisted.received == 1
    assert persisted.processed == 1


def test_repository_retry_outcome_preserved(
    orchestrator, run_id, opportunity
):

    outcome = Mock()

    outcome.outcome = "duplicate"
    outcome.original_outcome = "inserted"

    orchestrator.opportunities.ingest.return_value = (
        outcome
    )

    persisted = orchestrator.persist_accepted(
        make_result(run_id, (opportunity,))
    )

    assert persisted.received == 1
    assert persisted.outcomes == (outcome,)


def test_storage_failure_is_not_silenced(
    orchestrator, run_id, opportunity
):

    orchestrator.opportunities.ingest.side_effect = (
        RuntimeError("Storage failure")
    )

    with pytest.raises(RuntimeError):

        orchestrator.persist_accepted(
            make_result(run_id, (opportunity,))
        )

    orchestrator.runs.finish_run.assert_not_called()


def test_collection_failure_is_not_silenced(
    orchestrator, scraper, run_id
):

    scraper.run_with_result.side_effect = (
        RuntimeError("Collection failure")
    )

    with pytest.raises(RuntimeError):

        orchestrator.collect(
            scraper=scraper,
            run_id=run_id,
        )

    orchestrator.opportunities.ingest.assert_not_called()

    orchestrator.runs.finish_run.assert_not_called()


def test_finalized_run_prevents_persistence(
    orchestrator, run_id, opportunity
):

    orchestrator.runs.get_run.return_value = {
        "source_name": "wuzzuf",
        "status": "completed",
    }

    with pytest.raises(ValueError):

        orchestrator.persist_accepted(
            make_result(run_id, (opportunity,))
        )

    orchestrator.opportunities.ingest.assert_not_called()


def test_persistence_does_not_finalize_run(
    orchestrator, run_id, opportunity
):

    orchestrator.persist_accepted(
        make_result(run_id, (opportunity,))
    )

    orchestrator.runs.finish_run.assert_not_called()

    orchestrator.invalid_records.record.assert_not_called()
