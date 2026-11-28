from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest

from scrapers.collection_result import (
    CollectionResult,
    CollectionStatus,
    StopReason,
)

from scrapers.storage.postgres import PostgresStorage

from scrapers.storage.collection_snapshot import (
    CollectionSnapshotStore,
)

from scrapers.storage.snapshot_retention import (
    SnapshotRetentionManager,
)

from scrapers.storage.recovery_lock import (
    RecoveryAlreadyRunningError,
)


@pytest.fixture
def context(tmp_path):

    run_id = uuid4()

    store = CollectionSnapshotStore(
        tmp_path / "snapshots",
        integrity_key=b"x" * 32,
    )

    result = CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        status=CollectionStatus.COMPLETED,
        stop_reason=StopReason.INPUT_EXHAUSTED,
    )

    path = store.save(result)

    manager = SnapshotRetentionManager(
        Mock(spec=PostgresStorage),
        store,
        retention_days=30,
    )

    run = {
        "run_id": run_id,
        "source_name": "wuzzuf",
        "status": "completed",
        "finished_at": (
            datetime.now(timezone.utc)
            - timedelta(days=31)
        ),
        "records_received": 0,
        "records_inserted": 0,
        "records_updated": 0,
        "records_unchanged": 0,
        "records_invalid": 0,
        "records_stale": 0,
        "records_conflicted": 0,
    }

    manager.runs.get_run = Mock(
        return_value=run
    )

    manager.recovery_lock.acquire = Mock(
        side_effect=lambda *args, **kwargs: nullcontext()
    )

    return manager, store, run, path


def test_default_cleanup_is_dry_run(context):

    manager, store, run, path = context

    result = manager.cleanup()

    assert result.dry_run is True
    assert result.eligible == 1
    assert result.deleted == 0
    assert result.reclaimed_bytes == 0
    assert path.exists()


def test_expired_completed_snapshot_deleted(context):

    manager, store, run, path = context

    size = path.stat().st_size

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 1
    assert result.eligible == 1
    assert result.errors == 0
    assert result.reclaimed_bytes == size
    assert not path.exists()

    manager.recovery_lock.acquire.assert_called_once_with(
        run["run_id"],
        bind_connection=True,
    )


def test_repeated_cleanup_is_safe(context):

    manager, store, run, path = context

    first = manager.cleanup(dry_run=False)
    second = manager.cleanup(dry_run=False)

    assert first.deleted == 1
    assert second.deleted == 0
    assert second.scanned == 0
    assert second.errors == 0


@pytest.mark.parametrize(
    "status",
    ["running", "partial", "failed", "aborted"],
)
def test_non_completed_runs_retained(context, status):

    manager, store, run, path = context

    run["status"] = status

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.retained == 1
    assert result.decisions[0].reason == "run_not_completed"
    assert path.exists()


def test_recent_snapshot_retained(context):

    manager, store, run, path = context

    run["finished_at"] = datetime.now(timezone.utc)

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.decisions[0].reason == "within_retention_period"
    assert path.exists()


def test_unknown_run_retained(context):

    manager, store, run, path = context

    manager.runs.get_run.return_value = None

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.decisions[0].reason == "unknown_run"
    assert path.exists()


def test_corrupted_snapshot_retained(context):

    manager, store, run, path = context

    path.write_bytes(b"corrupted")

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.decisions[0].reason == (
        "snapshot_verification_failed"
    )

    assert path.read_bytes() == b"corrupted"


def test_database_identity_mismatch(context):

    manager, store, run, path = context

    run["run_id"] = uuid4()

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.decisions[0].reason == "database_run_mismatch"
    assert path.exists()


def test_source_mismatch(context):

    manager, store, run, path = context

    run["source_name"] = "bayt"

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.decisions[0].reason == "snapshot_run_mismatch"
    assert path.exists()


@pytest.mark.parametrize(
    "value",
    [None, -1, True, "0"],
)
def test_invalid_counters_block_deletion(context, value):

    manager, store, run, path = context

    run["records_received"] = value

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.decisions[0].reason == "invalid_run_counters"
    assert path.exists()


def test_inconsistent_counters_block_deletion(context):

    manager, store, run, path = context

    run["records_received"] = 5

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.decisions[0].reason == (
        "inconsistent_run_counters"
    )

    assert path.exists()


def test_active_recovery_blocks_deletion(context):

    manager, store, run, path = context

    manager.recovery_lock.acquire.side_effect = (
        RecoveryAlreadyRunningError("Run locked")
    )

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.skipped == 1
    assert result.decisions[0].reason == (
        "recovery_lock_unavailable"
    )

    manager.runs.get_run.assert_not_called()

    assert path.exists()


def test_database_failure_blocks_deletion(context):

    manager, store, run, path = context

    manager.runs.get_run.side_effect = RuntimeError(
        "Database unavailable"
    )

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.errors == 1
    assert path.exists()


def test_custom_time_blocked_during_deletion(context):

    manager, store, run, path = context

    with pytest.raises(ValueError):

        manager.cleanup(
            dry_run=False,
            now=datetime.now(timezone.utc)
            + timedelta(days=100),
        )

    assert path.exists()


def test_unrecognized_file_not_deleted(context):

    manager, store, run, path = context

    unrelated = store.directory / "important.txt"

    unrelated.write_text(
        "Keep this file",
        encoding="utf-8",
    )

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 1
    assert result.skipped == 1
    assert unrelated.exists()


def test_directory_not_deleted(context):

    manager, store, run, path = context

    path.unlink()
    path.mkdir()

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.skipped == 1
    assert path.is_dir()


def test_file_changed_during_verification(context):

    manager, store, run, path = context

    original_load = store.load

    def modified_load(run_id):

        result = original_load(run_id)

        with path.open("ab") as file:
            file.write(b"modified")

        return result

    store.load = Mock(side_effect=modified_load)

    result = manager.cleanup(dry_run=False)

    assert result.deleted == 0
    assert result.decisions[0].reason == "snapshot_changed"
    assert path.exists()
