import os

from unittest.mock import Mock

import pytest

from scrapers.storage.orchestrator import (
    IngestionExecutionError,
)

from scrapers.storage.concurrency import (
    ConcurrencyManager,
    WAREHOUSE_KEY,
)

from test_incremental_pipeline import (
    pipeline,
    make_scraper,
    execute,
)

from test_batch_recovery import (
    assert_counts,
    assert_completed,
)

from test_publication_gate_postgres import (
    connection_factory,
)

from test_protected_warehouse import module


pytestmark = pytest.mark.skipif(
    os.environ.get(
        "MATCHPOINT_RUN_CONCURRENCY_TESTS"
    ) != "1",
    reason="Requires isolated PostgreSQL database",
)


def test_partial_persistence_blocks_warehouse_until_recovery(
    pipeline,
    connection_factory,
    monkeypatch,
):

    orchestrator = pipeline["orchestrator"]

    assert orchestrator.recovery_lock is not None
    assert orchestrator.snapshot_store is not None

    orchestrator.batch_size = 2

    run_id = pipeline["run_id"]

    manager = ConcurrencyManager(
        connection_factory,
        timeout=2,
    )

    repository = orchestrator.opportunities

    original = repository.ingest_many

    calls = 0

    def fail_second_batch(records, active_run_id):

        nonlocal calls

        calls += 1

        assert active_run_id == run_id

        if calls == 2:

            assert_counts(pipeline, 2)

            with connection_factory() as observer:

                acquired = observer.execute(
                    "SELECT pg_try_advisory_lock(%s::bigint)",
                    (WAREHOUSE_KEY,),
                ).fetchone()[0]

                assert not acquired, (
                    "Warehouse lock acquired between batches"
                )

            raise RuntimeError(
                "Injected second batch failure"
            )

        return original(records, active_run_id)

    monkeypatch.setattr(
        repository,
        "ingest_many",
        fail_second_batch,
    )

    with pytest.raises(
        IngestionExecutionError
    ) as error:

        execute(
            pipeline,
            make_scraper(),
        )

    assert error.value.stage == "accepted_persistence"

    assert calls == 2

    assert_counts(pipeline, 2)

    assert pipeline["checkpoint"]() is None

    snapshot = orchestrator.snapshot_store.load(run_id)

    assert snapshot.run_id == run_id
    assert snapshot.accepted_count == 3

    print("PASS: First batch committed")
    print("PASS: Warehouse excluded between batches")
    print("PASS: Durable snapshot preserved")

    runner = Mock()

    with pytest.raises(
        module.PublicationBlockedError
    ) as blocked:

        module.execute_protected(
            manager,
            runner,
            publication_gate=module.verify_publication_ready,
        )

    assert str(run_id) in str(blocked.value)

    runner.assert_not_called()

    print("PASS: Partial run blocks warehouse publication")

    recovery = pipeline["new_orchestrator"]()

    recovery.batch_size = 100

    result = recovery.recover_with_retry(
        run_id=run_id,
    )

    assert_completed(pipeline, result)

    print("PASS: Recovery completed from snapshot")
    print("PASS: Checkpoint advanced safely")
    print("PASS: No duplicate listings or observations")

    stages = []

    def successful_stage(stage, connection):

        stages.append(stage)

        return 0

    assert module.execute_protected(
        manager,
        successful_stage,
        publication_gate=module.verify_publication_ready,
    ) == 0

    assert stages == ["seed", "run", "test"]

    print("PASS: Publication allowed after recovery")

    repeated = recovery.recover_with_retry(
        run_id=run_id,
    )

    assert repeated.already_finalized

    assert repeated.finalized_run == result.finalized_run

    assert_counts(pipeline, 3)

    print("PASS: Repeated recovery is idempotent")

    with connection_factory() as observer:

        assert observer.execute(
            "SELECT pg_try_advisory_lock(%s::bigint)",
            (WAREHOUSE_KEY,),
        ).fetchone()[0]

        assert observer.execute(
            "SELECT pg_advisory_unlock(%s::bigint)",
            (WAREHOUSE_KEY,),
        ).fetchone()[0]

    print("PASS: No warehouse lock leaks")


def test_automatic_warehouse_timeout_recovery(
    pipeline,
    monkeypatch,
):

    from contextlib import contextmanager
    from psycopg.errors import LockNotAvailable
    from scrapers.storage import persistence_guard as guard_module

    orchestrator = pipeline["orchestrator"]
    run_id = pipeline["run_id"]

    original_guard = guard_module.persistence_guard
    attempts = []

    @contextmanager
    def timeout_once(storage, active_run_id):

        assert active_run_id == run_id

        attempts.append(active_run_id)

        if len(attempts) == 1:

            snapshot = orchestrator.snapshot_store.load(run_id)

            assert snapshot.run_id == run_id
            assert snapshot.accepted_count == 3

            assert_counts(pipeline, 0)

            error = LockNotAvailable(
                "Injected warehouse lock timeout"
            )

            assert error.sqlstate == "55P03"

            raise error

        with original_guard(storage, active_run_id) as connection:
            yield connection

    monkeypatch.setattr(
        guard_module,
        "persistence_guard",
        timeout_once,
    )

    scraper = make_scraper()

    original_scrape = scraper.scrape
    collections = []

    def counted_scrape(*args, **kwargs):

        collections.append(1)

        return original_scrape(*args, **kwargs)

    monkeypatch.setattr(
        scraper,
        "scrape",
        counted_scrape,
    )

    original_execute = orchestrator.execute

    automatic_execute = orchestrator.execute_with_recovery

    # Support the existing fixture helper without
    # recursively invoking execute_with_recovery.

    def execute_original(*args, **kwargs):
        return original_execute(*args, **kwargs)

    def execute_automatically(*args, **kwargs):

        assert not args

        monkeypatch.setattr(
            orchestrator,
            "execute",
            execute_original,
        )

        return automatic_execute(**kwargs)

    monkeypatch.setattr(
        orchestrator,
        "execute",
        execute_automatically,
    )

    result = execute(pipeline, scraper)

    assert len(attempts) == 2
    assert len(collections) == 1

    assert_completed(pipeline, result)
    assert_counts(pipeline, 3)

    print("PASS: SQLSTATE 55P03 handled automatically")
    print("PASS: Snapshot recovered without rescraping")
    print("PASS: Exactly one collection execution")
    print("PASS: Checkpoint and counters consistent")
