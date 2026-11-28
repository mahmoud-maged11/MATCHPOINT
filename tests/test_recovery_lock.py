import os

from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.recovery_lock import (
    RecoveryLockManager,
    RecoveryAlreadyRunningError,
)

from scrapers.storage.orchestrator import (
    IngestionOrchestrator,
    IngestionExecutionError,
)


@pytest.fixture
def storage():

    if os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests disabled")

    storage = PostgresStorage(
        PostgresSettings.from_config(
            host="127.0.0.1",
            database="matchpoint_ingestion_test",
        )
    )

    with storage.transaction() as connection:

        row = connection.execute(
            "SELECT current_database() AS database"
        ).fetchone()

        assert row["database"] == (
            "matchpoint_ingestion_test"
        )

    return storage


@pytest.fixture
def manager(storage):

    return RecoveryLockManager(storage)


def test_deterministic_lock_key():

    run_id = uuid4()

    assert RecoveryLockManager.lock_key(run_id) == (
        RecoveryLockManager.lock_key(run_id)
    )


def test_lock_key_signed_bigint():

    for _ in range(100):

        key = RecoveryLockManager.lock_key(uuid4())

        assert -(2 ** 63) <= key < 2 ** 63


@pytest.mark.parametrize(
    "run_id",
    [None, "", "invalid", 123],
)
def test_invalid_lock_identity(run_id):

    with pytest.raises(TypeError):
        RecoveryLockManager.lock_key(run_id)


def test_same_run_lock_conflict(manager):

    run_id = uuid4()

    with manager.acquire(run_id):

        with pytest.raises(RecoveryAlreadyRunningError):

            with manager.acquire(run_id):
                pytest.fail("Duplicate lock acquired")


def test_different_runs_can_execute(manager):

    with manager.acquire(uuid4()):

        with manager.acquire(uuid4()):
            pass


def test_lock_released_after_success(manager):

    run_id = uuid4()

    with manager.acquire(run_id):
        pass

    with manager.acquire(run_id):
        pass


def test_lock_released_after_failure(manager):

    run_id = uuid4()

    with pytest.raises(ValueError):

        with manager.acquire(run_id):
            raise ValueError("Simulated failure")

    with manager.acquire(run_id):
        pass


def test_lock_released_after_interrupt(manager):

    run_id = uuid4()

    with pytest.raises(KeyboardInterrupt):

        with manager.acquire(run_id):
            raise KeyboardInterrupt()

    with manager.acquire(run_id):
        pass


def test_concurrent_thread_blocked(manager):

    run_id = uuid4()

    def attempt():

        try:
            with manager.acquire(run_id):
                return "acquired"

        except RecoveryAlreadyRunningError:
            return "blocked"

    with manager.acquire(run_id):

        with ThreadPoolExecutor(
            max_workers=1
        ) as executor:

            future = executor.submit(attempt)

            assert future.result(timeout=10) == "blocked"


def test_independent_managers_share_lock(storage):

    first = RecoveryLockManager(storage)
    second = RecoveryLockManager(storage)

    run_id = uuid4()

    with first.acquire(run_id):

        with pytest.raises(RecoveryAlreadyRunningError):

            with second.acquire(run_id):
                pytest.fail("Duplicate lock acquired")


def test_orchestrator_lock_conflict(storage, manager):

    run_id = uuid4()

    orchestrator = IngestionOrchestrator(
        storage,
        recovery_lock=manager,
    )

    with manager.acquire(run_id):

        with pytest.raises(IngestionExecutionError) as error:

            with orchestrator._acquire_run_lock(run_id):
                pytest.fail("Execution should be blocked")

    assert error.value.run_id == run_id

    assert error.value.stage == "recovery_lock"

    assert isinstance(
        error.value.__cause__,
        RecoveryAlreadyRunningError,
    )


def test_orchestrator_preserves_execution_error(
    storage,
    manager,
):
    run_id = uuid4()

    orchestrator = IngestionOrchestrator(
        storage,
        recovery_lock=manager,
    )

    original_error = ValueError("Execution failure")

    with pytest.raises(ValueError) as error:

        with orchestrator._acquire_run_lock(run_id):
            raise original_error

    assert error.value is original_error

    with manager.acquire(run_id):
        pass


def test_orchestrator_holds_lock_during_execution(
    storage,
    manager,
):
    run_id = uuid4()

    orchestrator = IngestionOrchestrator(
        storage,
        recovery_lock=manager,
    )

    with orchestrator._acquire_run_lock(run_id):

        with pytest.raises(RecoveryAlreadyRunningError):

            with manager.acquire(run_id):
                pytest.fail("Execution lock was not held")

    with manager.acquire(run_id):
        pass


@pytest.fixture
def protected_context(storage, manager, tmp_path):

    from scrapers.storage.collection_snapshot import (
        CollectionSnapshotStore,
    )

    from scrapers.storage.rejection_policy import (
        RejectionPolicy,
    )

    from scrapers.sources.wuzzuf import WuzzufScraper

    store = CollectionSnapshotStore(
        tmp_path / "snapshots",
        integrity_key=b"x" * 32,
    )

    orchestrator = IngestionOrchestrator(
        storage,
        rejection_policy=RejectionPolicy(
            fingerprint_key=b"y" * 32,
        ),
        snapshot_store=store,
        recovery_lock=manager,
    )

    scraper = WuzzufScraper(
        html_path="tests/fixtures/wuzzuf_synthetic.html"
    )

    return orchestrator, scraper, store


def test_execute_blocked_before_run_creation(
    protected_context,
    manager,
    monkeypatch,
):
    from unittest.mock import Mock

    orchestrator, scraper, store = protected_context

    run_id = uuid4()

    start = Mock()
    collect = Mock()

    monkeypatch.setattr(
        orchestrator,
        "start_collection",
        start,
    )

    monkeypatch.setattr(
        orchestrator,
        "collect",
        collect,
    )

    with manager.acquire(run_id):

        with pytest.raises(IngestionExecutionError) as error:

            orchestrator.execute(
                scraper=scraper,
                collection_mode="html",
                run_id=run_id,
            )

    assert error.value.stage == "recovery_lock"
    assert error.value.run_id == run_id

    start.assert_not_called()
    collect.assert_not_called()

    assert not store.exists(run_id)


def test_recovery_blocked_before_snapshot_loading(
    protected_context,
    manager,
    monkeypatch,
):
    from unittest.mock import Mock

    orchestrator, scraper, store = protected_context

    run_id = uuid4()

    load = Mock()

    monkeypatch.setattr(store, "load", load)

    with manager.acquire(run_id):

        with pytest.raises(IngestionExecutionError) as error:

            orchestrator.recover(run_id=run_id)

    assert error.value.stage == "recovery_lock"

    load.assert_not_called()


def test_execute_holds_lock_through_persistence(
    protected_context,
    manager,
    monkeypatch,
):
    from unittest.mock import Mock

    orchestrator, scraper, store = protected_context

    run_id = uuid4()

    result = scraper.run_with_result(
        run_id=run_id
    )

    def assert_locked():

        with pytest.raises(RecoveryAlreadyRunningError):

            with manager.acquire(run_id):
                pytest.fail("Execution lock was lost")

    def start(**kwargs):

        assert_locked()

        return run_id

    def collect(**kwargs):

        assert_locked()

        return result

    execution = Mock()
    execution.run_id = run_id

    def persist(collection):

        assert_locked()

        assert collection == result

        return execution

    monkeypatch.setattr(
        orchestrator,
        "start_collection",
        start,
    )

    monkeypatch.setattr(
        orchestrator,
        "collect",
        collect,
    )

    monkeypatch.setattr(
        orchestrator,
        "persist_collection",
        persist,
    )

    response = orchestrator.execute(
        scraper=scraper,
        collection_mode="html",
        run_id=run_id,
    )

    assert response is execution

    with manager.acquire(run_id):
        pass


def test_recovery_holds_lock_through_persistence(
    protected_context,
    manager,
    monkeypatch,
):
    from unittest.mock import Mock

    orchestrator, scraper, store = protected_context

    run_id = uuid4()

    result = scraper.run_with_result(
        run_id=run_id
    )

    store.save(result)

    def assert_locked():

        with pytest.raises(RecoveryAlreadyRunningError):

            with manager.acquire(run_id):
                pytest.fail("Recovery lock was lost")

    def validate(requested_run_id):

        assert requested_run_id == run_id
        assert_locked()

        return {
            "run_id": run_id,
            "source_name": result.source_name,
            "status": "running",
        }

    execution = Mock()
    execution.run_id = run_id

    def persist(collection):

        assert_locked()

        assert collection == result

        return execution

    monkeypatch.setattr(
        orchestrator.runs,
        "get_run",
        validate,
    )

    monkeypatch.setattr(
        orchestrator,
        "persist_collection",
        persist,
    )

    response = orchestrator.recover(
        run_id=run_id
    )

    assert response.execution is execution
    assert response.run_id == run_id
    assert response.collection_result == result
    assert response.already_finalized is False

    with manager.acquire(run_id):
        pass


def test_recovery_failure_releases_lock(
    protected_context,
    manager,
    monkeypatch,
):
    from unittest.mock import Mock

    orchestrator, scraper, store = protected_context

    run_id = uuid4()

    result = scraper.run_with_result(
        run_id=run_id
    )

    store.save(result)

    monkeypatch.setattr(
        orchestrator.runs,
        "get_run",
        Mock(return_value={
            "run_id": run_id,
            "source_name": result.source_name,
            "status": "running",
        }),
    )

    monkeypatch.setattr(
        orchestrator,
        "persist_collection",
        Mock(
            side_effect=RuntimeError(
                "Simulated persistence failure"
            )
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated persistence failure",
    ):
        orchestrator.recover(run_id=run_id)

    assert store.load(run_id) == result

    with manager.acquire(run_id):
        pass

def test_finalized_recovery_holds_and_releases_lock(
    protected_context,
    manager,
    monkeypatch,
):
    from unittest.mock import Mock

    orchestrator, scraper, store = protected_context

    run_id = uuid4()

    result = scraper.run_with_result(
        run_id=run_id
    )

    store.save(result)

    finalized = {
        "run_id": run_id,
        "source_name": result.source_name,
        "status": result.status.value,
        "records_received": result.returned_count,
    }

    def get_run(requested_run_id):

        assert requested_run_id == run_id

        with pytest.raises(RecoveryAlreadyRunningError):

            with manager.acquire(run_id):

                pytest.fail(
                    "Finalized recovery lost its lock"
                )

        return finalized

    persist = Mock(
        side_effect=AssertionError(
            "Finalized recovery must not persist"
        )
    )

    monkeypatch.setattr(
        orchestrator.runs,
        "get_run",
        get_run,
    )

    monkeypatch.setattr(
        orchestrator,
        "persist_collection",
        persist,
    )

    response = orchestrator.recover(
        run_id=run_id
    )

    assert response.already_finalized is True
    assert response.finalized_run == finalized
    assert response.execution is None

    persist.assert_not_called()

    with manager.acquire(run_id):
        pass
