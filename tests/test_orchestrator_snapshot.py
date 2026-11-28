from uuid import uuid4
from unittest.mock import Mock

import pytest

from scrapers.sources.wuzzuf import WuzzufScraper

from scrapers.storage.postgres import (
    PostgresStorage,
    PostgresSettings,
)

from scrapers.storage.orchestrator import (
    IngestionOrchestrator,
    IngestionExecutionError,
)

from scrapers.storage.collection_snapshot import (
    CollectionSnapshotStore,
    SnapshotConflictError,
)

from scrapers.storage.rejection_policy import (
    RejectionPolicy,
)


@pytest.fixture
def context(tmp_path, monkeypatch):

    store = CollectionSnapshotStore(
        tmp_path / "snapshots",
        integrity_key=b"x" * 32,
    )

    storage = Mock(spec=PostgresStorage)

    orchestrator = IngestionOrchestrator(
        storage,
        rejection_policy=RejectionPolicy(
            fingerprint_key=b"y" * 32,
        ),
        snapshot_store=store,
    )

    result = WuzzufScraper(
        html_path="tests/fixtures/wuzzuf_synthetic.html"
    ).run_with_result(run_id=uuid4())

    assert result.accepted_count == 3
    assert result.rejected_count == 2

    monkeypatch.setattr(
        orchestrator,
        "validate_run",
        Mock(return_value={
            "run_id": result.run_id,
            "source_name": result.source_name,
            "status": "running",
        }),
    )

    accepted = Mock()
    accepted.received = 3
    accepted.duplicate_inputs = 0

    rejected = Mock()
    rejected.received = 2
    rejected.duplicate_inputs = 0

    monkeypatch.setattr(
        orchestrator,
        "persist_accepted",
        Mock(return_value=accepted),
    )

    monkeypatch.setattr(
        orchestrator,
        "persist_rejected",
        Mock(return_value=rejected),
    )

    monkeypatch.setattr(
        type(orchestrator.run_recovery),
        "finish_run",
        Mock(return_value={
            "run_id": result.run_id,
            "status": "completed",
            "records_received": 5,
        }),
    )

    return orchestrator, store, result


def test_snapshot_saved_before_persistence(context):

    orchestrator, store, result = context

    def persist(prepared):

        assert store.exists(result.run_id)

        assert store.load(result.run_id) == result

        response = Mock()
        response.received = 3
        response.duplicate_inputs = 0

        return response

    orchestrator.persist_accepted.side_effect = persist

    execution = orchestrator.persist_collection(result)

    assert execution.run_id == result.run_id
    assert execution.received == 5

    assert store.load(result.run_id) == result

    orchestrator.persist_accepted.assert_called_once()
    orchestrator.persist_rejected.assert_called_once()

    orchestrator.run_recovery.finish_run.assert_called_once()


def test_snapshot_failure_blocks_persistence(
    context,
    monkeypatch,
):
    orchestrator, store, result = context

    monkeypatch.setattr(
        store,
        "save",
        Mock(side_effect=OSError("Disk failure")),
    )

    with pytest.raises(IngestionExecutionError) as error:
        orchestrator.persist_collection(result)

    assert error.value.stage == "snapshot_persistence"
    assert error.value.run_id == result.run_id

    assert not store.exists(result.run_id)

    orchestrator.persist_accepted.assert_not_called()
    orchestrator.persist_rejected.assert_not_called()

    orchestrator.run_recovery.finish_run.assert_not_called()


@pytest.mark.parametrize(
    "stage",
    [
        "accepted_persistence",
        "rejected_persistence",
        "finalization",
    ],
)
def test_snapshot_survives_persistence_failure(
    context,
    stage,
):
    orchestrator, store, result = context

    operations = {
        "accepted_persistence": (
            orchestrator.persist_accepted
        ),
        "rejected_persistence": (
            orchestrator.persist_rejected
        ),
        "finalization": (
            orchestrator.run_recovery.finish_run
        ),
    }

    operations[stage].side_effect = RuntimeError(
        "Simulated database failure"
    )

    with pytest.raises(IngestionExecutionError) as error:
        orchestrator.persist_collection(result)

    assert error.value.stage == stage
    assert error.value.run_id == result.run_id

    assert store.exists(result.run_id)
    assert store.load(result.run_id) == result


def test_snapshot_conflict_blocks_persistence(context):

    from dataclasses import replace

    from scrapers.collection_result import (
        CollectionStatus,
        StopReason,
    )

    orchestrator, store, result = context

    original = replace(
        result,
        status=CollectionStatus.PARTIAL,
        stop_reason=StopReason.SOURCE_ERROR,
    )

    store.save(original)

    with pytest.raises(IngestionExecutionError) as error:
        orchestrator.persist_collection(result)

    assert error.value.stage == "snapshot_persistence"

    assert isinstance(
        error.value.__cause__,
        SnapshotConflictError,
    )

    assert store.load(result.run_id) == original

    orchestrator.persist_accepted.assert_not_called()
    orchestrator.persist_rejected.assert_not_called()

    orchestrator.run_recovery.finish_run.assert_not_called()


def test_snapshot_retained_after_success(context):

    orchestrator, store, result = context

    execution = orchestrator.persist_collection(result)

    assert execution.finalized_run["status"] == "completed"

    assert store.exists(result.run_id)

    assert store.load(result.run_id) == result


def test_preparation_failure_creates_no_snapshot(context):

    orchestrator, store, result = context

    orchestrator.validate_run.side_effect = ValueError(
        "Invalid run"
    )

    with pytest.raises(IngestionExecutionError) as error:
        orchestrator.persist_collection(result)

    assert error.value.stage == "preparation"

    assert not store.exists(result.run_id)

    orchestrator.persist_accepted.assert_not_called()
    orchestrator.persist_rejected.assert_not_called()


def test_retry_preserves_original_snapshot(context):

    orchestrator, store, result = context

    orchestrator.persist_accepted.side_effect = RuntimeError(
        "Temporary database failure"
    )

    with pytest.raises(IngestionExecutionError):
        orchestrator.persist_collection(result)

    path = store.directory / f"{result.run_id}.json"

    original_content = path.read_bytes()

    orchestrator.persist_accepted.side_effect = None

    restored = store.load(result.run_id)

    execution = orchestrator.persist_collection(restored)

    assert execution.run_id == result.run_id

    assert execution.finalized_run["status"] == "completed"

    assert path.read_bytes() == original_content

    assert store.load(result.run_id) == result