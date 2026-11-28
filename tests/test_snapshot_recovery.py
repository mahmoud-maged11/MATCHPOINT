from unittest.mock import Mock
from uuid import uuid4

import pytest

from scrapers.sources.wuzzuf import WuzzufScraper

from scrapers.storage.postgres import PostgresStorage

from scrapers.storage.orchestrator import (
    IngestionOrchestrator,
    IngestionExecutionError,
)

from scrapers.storage.collection_snapshot import (
    CollectionSnapshotStore,
    SnapshotError,
    SnapshotIntegrityError,
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
    ).run_with_result(
        run_id=uuid4()
    )

    assert result.accepted_count == 3
    assert result.rejected_count == 2

    store.save(result)

    monkeypatch.setattr(
        orchestrator.runs,
        "get_run",
        Mock(return_value={
            "run_id": result.run_id,
            "source_name": result.source_name,
            "status": "running",
        }),
    )

    execution = Mock()
    execution.run_id = result.run_id
    execution.collection_status = result.status
    execution.stop_reason = result.stop_reason
    execution.finalized_run = {
        "run_id": result.run_id,
        "source_name": result.source_name,
        "status": result.status.value,
        "records_received": result.returned_count,
    }

    monkeypatch.setattr(
        orchestrator,
        "persist_collection",
        Mock(return_value=execution),
    )

    return orchestrator, store, result


def test_recover_original_run(context):

    orchestrator, store, result = context

    execution = orchestrator.recover(
        run_id=result.run_id
    )

    assert execution.run_id == result.run_id

    orchestrator.runs.get_run.assert_called_once_with(
        result.run_id
    )

    assert execution.already_finalized is False
    assert execution.collection_result == result
    assert execution.execution is (
        orchestrator.persist_collection.return_value
    )

    orchestrator.persist_collection.assert_called_once_with(
        result
    )


def test_recovery_does_not_collect_again(
    context,
    monkeypatch,
):
    orchestrator, store, result = context

    collect = Mock(
        side_effect=AssertionError(
            "Recovery must not collect again"
        )
    )

    monkeypatch.setattr(
        orchestrator,
        "collect",
        collect,
    )

    orchestrator.recover(
        run_id=result.run_id
    )

    collect.assert_not_called()

    orchestrator.persist_collection.assert_called_once()


def test_recovery_preserves_original_timestamps(context):

    orchestrator, store, result = context

    orchestrator.recover(
        run_id=result.run_id
    )

    restored = (
        orchestrator.persist_collection.call_args.args[0]
    )

    for original, recovered in zip(
        result.opportunities,
        restored.opportunities,
        strict=True,
    ):
        assert original.collected_at == recovered.collected_at

    for original, recovered in zip(
        result.invalid_records,
        restored.invalid_records,
        strict=True,
    ):
        assert original.collected_at == recovered.collected_at


def test_recovery_preserves_observation_hashes(context):

    from scrapers.utils.hashing import (
        generate_observation_hash,
    )

    orchestrator, store, result = context

    orchestrator.recover(
        run_id=result.run_id
    )

    restored = (
        orchestrator.persist_collection.call_args.args[0]
    )

    for original, recovered in zip(
        result.opportunities,
        restored.opportunities,
        strict=True,
    ):
        assert generate_observation_hash(original) == (
            generate_observation_hash(recovered)
        )


def test_missing_snapshot_blocks_recovery(context):

    orchestrator, store, result = context

    missing_id = uuid4()

    orchestrator.runs.get_run.return_value = None

    with pytest.raises(IngestionExecutionError) as error:
        orchestrator.recover(
            run_id=missing_id
        )

    assert error.value.run_id == missing_id
    assert error.value.stage == "snapshot_loading"

    assert isinstance(
        error.value.__cause__,
        SnapshotError,
    )

    orchestrator.runs.get_run.assert_called_once_with(missing_id)
    orchestrator.persist_collection.assert_not_called()


def test_corrupted_snapshot_blocks_recovery(context):

    orchestrator, store, result = context

    path = store.directory / f"{result.run_id}.json"

    path.write_bytes(b"corrupted")

    with pytest.raises(IngestionExecutionError) as error:
        orchestrator.recover(
            run_id=result.run_id
        )

    assert error.value.stage == "snapshot_loading"

    assert isinstance(
        error.value.__cause__,
        SnapshotIntegrityError,
    )

    orchestrator.runs.get_run.assert_not_called()
    orchestrator.persist_collection.assert_not_called()


def test_wrong_key_blocks_recovery(context):

    orchestrator, store, result = context

    orchestrator.snapshot_store = CollectionSnapshotStore(
        store.directory,
        integrity_key=b"z" * 32,
    )

    with pytest.raises(IngestionExecutionError) as error:
        orchestrator.recover(
            run_id=result.run_id
        )

    assert error.value.stage == "snapshot_loading"

    orchestrator.persist_collection.assert_not_called()


@pytest.mark.parametrize(
    "scenario",
    [
        "missing_run",
        "source_mismatch",
        "status_failed",
        "status_aborted",
        "status_partial",
        "unsupported_status",
    ],
)
def test_recovery_validation_failure(
    context,
    scenario,
):

    orchestrator, store, result = context

    run = {
        "run_id": result.run_id,
        "source_name": result.source_name,
        "status": "running",
    }

    if scenario == "missing_run":

        run = None

    elif scenario == "source_mismatch":

        run["source_name"] = "bayt"

    elif scenario == "unsupported_status":

        run["status"] = "invalid_status"

    else:

        run["status"] = scenario.removeprefix(
            "status_"
        )

    orchestrator.runs.get_run.return_value = run

    with pytest.raises(IngestionExecutionError) as error:

        orchestrator.recover(
            run_id=result.run_id
        )

    assert error.value.stage == "recovery_validation"
    assert error.value.run_id == result.run_id

    assert isinstance(
        error.value.__cause__,
        ValueError,
    )

    assert store.exists(result.run_id)

    orchestrator.persist_collection.assert_not_called()


def test_recovery_database_lookup_failure(context):

    orchestrator, store, result = context

    orchestrator.runs.get_run.side_effect = RuntimeError(
        "Database lookup failed"
    )

    with pytest.raises(IngestionExecutionError) as error:

        orchestrator.recover(
            run_id=result.run_id
        )

    assert error.value.stage == "recovery_validation"
    assert error.value.run_id == result.run_id
    assert store.exists(result.run_id)

    orchestrator.persist_collection.assert_not_called()


@pytest.mark.parametrize(
    "run_id",
    [
        None,
        "",
        "invalid",
        123,
    ],
)
def test_invalid_recovery_run_id(
    context,
    run_id,
):
    orchestrator, store, result = context

    with pytest.raises(TypeError):
        orchestrator.recover(
            run_id=run_id
        )

    orchestrator.persist_collection.assert_not_called()


def test_recovery_requires_snapshot_store(context):

    orchestrator, store, result = context

    orchestrator.snapshot_store = None

    with pytest.raises(RuntimeError):
        orchestrator.recover(
            run_id=result.run_id
        )

    orchestrator.persist_collection.assert_not_called()


def test_recovery_requires_rejection_policy(context):

    orchestrator, store, result = context

    orchestrator.rejection_policy = None

    with pytest.raises(RuntimeError):
        orchestrator.recover(
            run_id=result.run_id
        )

    orchestrator.persist_collection.assert_not_called()


def test_recovery_failure_retains_snapshot(context):

    orchestrator, store, result = context

    path = store.directory / f"{result.run_id}.json"

    original = path.read_bytes()

    orchestrator.persist_collection.side_effect = (
        IngestionExecutionError(
            run_id=result.run_id,
            stage="accepted_persistence",
            collection_result=result,
        )
    )

    with pytest.raises(IngestionExecutionError) as error:
        orchestrator.recover(
            run_id=result.run_id
        )

    assert error.value.stage == "accepted_persistence"

    assert path.read_bytes() == original

    assert store.load(result.run_id) == result

@pytest.mark.parametrize(
    "status,reason",
    [
        ("completed", "input_exhausted"),
        ("partial", "source_error"),
        ("failed", "source_error"),
        ("aborted", "interrupted"),
    ],
)
def test_finalized_recovery_is_read_only(
    context,
    monkeypatch,
    status,
    reason,
):
    from scrapers.collection_result import (
        CollectionResult,
        CollectionStatus,
        StopReason,
    )

    orchestrator, store, original = context

    result = CollectionResult(
        run_id=uuid4(),
        source_name=original.source_name,
        opportunities=(
            ()
            if status == "failed"
            else original.opportunities
        ),
        invalid_records=(),
        status=CollectionStatus(status),
        stop_reason=StopReason(reason),
    )

    store.save(result)

    finalized = {
        "run_id": result.run_id,
        "source_name": result.source_name,
        "status": status,
        "records_received": result.returned_count,
    }

    orchestrator.runs.get_run.return_value = finalized

    load = Mock(wraps=store.load)

    monkeypatch.setattr(
        store,
        "load",
        load,
    )

    path = store.directory / f"{result.run_id}.json"

    original_bytes = path.read_bytes()

    response = orchestrator.recover(
        run_id=result.run_id
    )

    assert response.run_id == result.run_id
    assert response.already_finalized is True
    assert response.collection_status == result.status
    assert response.stop_reason == result.stop_reason
    assert response.collection_result == result
    assert response.finalized_run == finalized
    assert response.received == result.returned_count

    assert response.execution is None
    assert response.accepted is None
    assert response.rejected is None
    assert response.duplicate_inputs is None

    load.assert_called_once_with(
        result.run_id
    )

    orchestrator.runs.get_run.assert_called_once_with(
        result.run_id
    )

    orchestrator.persist_collection.assert_not_called()

    assert path.read_bytes() == original_bytes


def test_running_recovery_loads_snapshot_once(
    context,
    monkeypatch,
):

    orchestrator, store, result = context

    load = Mock(wraps=store.load)

    monkeypatch.setattr(
        store,
        "load",
        load,
    )

    response = orchestrator.recover(
        run_id=result.run_id
    )

    load.assert_called_once_with(
        result.run_id
    )

    orchestrator.persist_collection.assert_called_once_with(
        result
    )

    assert response.already_finalized is False
    assert response.collection_result == result


def test_finalized_recovery_still_requires_valid_snapshot(
    context,
):

    orchestrator, store, result = context

    orchestrator.runs.get_run.return_value = {
        "run_id": result.run_id,
        "source_name": result.source_name,
        "status": result.status.value,
    }

    path = store.directory / f"{result.run_id}.json"

    path.write_bytes(b"tampered")

    with pytest.raises(IngestionExecutionError) as error:

        orchestrator.recover(
            run_id=result.run_id
        )

    assert error.value.stage == "snapshot_loading"

    orchestrator.persist_collection.assert_not_called()

    orchestrator.runs.get_run.assert_not_called()
