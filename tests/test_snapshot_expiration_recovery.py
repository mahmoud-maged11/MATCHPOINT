import json

from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest

from scrapers import main as cli

from scrapers.collection_result import CollectionStatus

from scrapers.storage.postgres import PostgresStorage

from scrapers.storage.orchestrator import (
    IngestionOrchestrator,
    IngestionExecutionError,
)

from scrapers.storage.collection_snapshot import (
    CollectionSnapshotStore,
    SnapshotNotFoundError,
    SnapshotIntegrityError,
)

from scrapers.storage.rejection_policy import (
    RejectionPolicy,
)


@pytest.fixture
def context(tmp_path):

    run_id = uuid4()

    store = CollectionSnapshotStore(
        tmp_path / "snapshots",
        integrity_key=b"x" * 32,
    )

    storage = Mock(spec=PostgresStorage)

    orchestrator = IngestionOrchestrator(
        storage,
        snapshot_store=store,
        rejection_policy=RejectionPolicy(
            fingerprint_key=b"y" * 32,
        ),
    )

    run = {
        "run_id": run_id,
        "source_name": "wuzzuf",
        "status": "completed",
        "finished_at": datetime.now(timezone.utc),
        "records_received": 5,
        "records_inserted": 3,
        "records_updated": 0,
        "records_unchanged": 0,
        "records_invalid": 2,
        "records_stale": 0,
        "records_conflicted": 0,
    }

    orchestrator.runs.get_run = Mock(
        return_value=run
    )

    orchestrator.persist_collection = Mock(
        side_effect=AssertionError(
            "Database-only recovery must not persist records"
        )
    )

    return orchestrator, store, run_id, run


def test_missing_snapshot_has_specific_error(context):

    orchestrator, store, run_id, run = context

    with pytest.raises(SnapshotNotFoundError):

        store.load(run_id)


def test_completed_run_without_snapshot(context):

    orchestrator, store, run_id, run = context

    recovery = orchestrator.recover(
        run_id=run_id
    )

    assert recovery.run_id == run_id

    assert recovery.already_finalized is True

    assert recovery.collection_status == (
        CollectionStatus.COMPLETED
    )

    assert recovery.collection_result is None
    assert recovery.stop_reason is None
    assert recovery.execution is None

    assert recovery.accepted is None
    assert recovery.rejected is None
    assert recovery.duplicate_inputs is None

    assert recovery.received == 5
    assert recovery.finalized_run == run

    orchestrator.persist_collection.assert_not_called()


def test_repeated_database_only_recovery(context):

    orchestrator, store, run_id, run = context

    first = orchestrator.recover(
        run_id=run_id
    )

    second = orchestrator.recover(
        run_id=run_id
    )

    assert first == second

    assert first.already_finalized is True

    orchestrator.persist_collection.assert_not_called()

    assert orchestrator.runs.get_run.call_count == 2


@pytest.mark.parametrize(
    "status",
    [
        "running",
        "partial",
        "failed",
        "aborted",
        "unsupported",
    ],
)
def test_non_completed_run_requires_snapshot(
    context,
    status,
):

    orchestrator, store, run_id, run = context

    run["status"] = status

    with pytest.raises(IngestionExecutionError) as error:

        orchestrator.recover(
            run_id=run_id
        )

    assert error.value.stage == "snapshot_loading"

    assert isinstance(
        error.value.__cause__,
        SnapshotNotFoundError,
    )

    orchestrator.persist_collection.assert_not_called()


def test_unknown_run_without_snapshot(context):

    orchestrator, store, run_id, run = context

    orchestrator.runs.get_run.return_value = None

    with pytest.raises(IngestionExecutionError) as error:

        orchestrator.recover(
            run_id=run_id
        )

    assert error.value.stage == "snapshot_loading"

    orchestrator.persist_collection.assert_not_called()


def test_database_run_identity_mismatch(context):

    orchestrator, store, run_id, run = context

    run["run_id"] = uuid4()

    with pytest.raises(IngestionExecutionError) as error:

        orchestrator.recover(
            run_id=run_id
        )

    assert error.value.stage == "recovery_validation"

    orchestrator.persist_collection.assert_not_called()


def test_completed_run_requires_finalization_timestamp(
    context,
):

    orchestrator, store, run_id, run = context

    run["finished_at"] = None

    with pytest.raises(IngestionExecutionError) as error:

        orchestrator.recover(
            run_id=run_id
        )

    assert error.value.stage == "recovery_validation"

    orchestrator.persist_collection.assert_not_called()


def test_corrupted_snapshot_cannot_use_database_fallback(
    context,
):

    orchestrator, store, run_id, run = context

    store.directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = store.directory / f"{run_id}.json"

    path.write_bytes(b"corrupted snapshot")

    with pytest.raises(IngestionExecutionError) as error:

        orchestrator.recover(
            run_id=run_id
        )

    assert error.value.stage == "snapshot_loading"

    assert isinstance(
        error.value.__cause__,
        SnapshotIntegrityError,
    )

    orchestrator.runs.get_run.assert_not_called()

    orchestrator.persist_collection.assert_not_called()

    assert path.read_bytes() == b"corrupted snapshot"


def test_directory_is_not_treated_as_missing_snapshot(
    context,
):

    orchestrator, store, run_id, run = context

    path = store.directory / f"{run_id}.json"

    path.mkdir(parents=True)

    with pytest.raises(IngestionExecutionError) as error:

        orchestrator.recover(
            run_id=run_id
        )

    assert isinstance(
        error.value.__cause__,
        SnapshotIntegrityError,
    )

    orchestrator.runs.get_run.assert_not_called()

    orchestrator.persist_collection.assert_not_called()


def test_database_failure_does_not_report_success(context):

    orchestrator, store, run_id, run = context

    orchestrator.runs.get_run.side_effect = RuntimeError(
        "Database unavailable"
    )

    with pytest.raises(IngestionExecutionError):

        orchestrator.recover(
            run_id=run_id
        )

    orchestrator.persist_collection.assert_not_called()


def test_database_only_cli_summary(
    context,
    monkeypatch,
    capsys,
):

    orchestrator, store, run_id, run = context

    monkeypatch.setattr(
        cli,
        "create_orchestrator",
        Mock(return_value=orchestrator),
    )

    scraper_factory = Mock(
        side_effect=AssertionError(
            "Recovery must not collect again"
        )
    )

    monkeypatch.setattr(
        cli,
        "create_scraper",
        scraper_factory,
    )

    code = cli.main([
        "--recover-run-id",
        str(run_id),
    ])

    assert code == 0

    summary = json.loads(
        capsys.readouterr().out
    )

    assert summary["run_id"] == str(run_id)
    assert summary["source"] == "wuzzuf"
    assert summary["operation"] == "recovery"
    assert summary["status"] == "completed"

    assert summary["already_finalized"] is True
    assert summary["snapshot_available"] is False

    assert summary["stop_reason"] is None
    assert summary["accepted"] is None
    assert summary["rejected"] is None

    assert summary["persistence_status"] == "finalized"
    assert summary["export_status"] == "not_requested"

    assert summary["counters"] == {
        "records_received": 5,
        "records_inserted": 3,
        "records_updated": 0,
        "records_unchanged": 0,
        "records_invalid": 2,
        "records_stale": 0,
        "records_conflicted": 0,
    }

    scraper_factory.assert_not_called()

    orchestrator.persist_collection.assert_not_called()
