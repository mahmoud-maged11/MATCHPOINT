
from unittest.mock import Mock

import pytest

from scrapers import main as cli
from scrapers import guarded_cli
from scrapers.source_lock import LocalSourceLock

from test_protected_warehouse import (
    module,
    FakeManager,
)


def test_default_cli_holds_source_lock(tmp_path, monkeypatch):

    manager = LocalSourceLock(tmp_path)

    class TestSourceLock(LocalSourceLock):

        def __init__(self):
            super().__init__(tmp_path)

    monkeypatch.setattr(
        guarded_cli,
        "LocalSourceLock",
        TestSourceLock,
    )

    def operation(args, mode):

        assert args.source == "bayt"

        assert guarded_cli.execute_guarded(
            "bayt",
            None,
            lambda: pytest.fail("Duplicate collection"),
            lock_manager=manager,
        ) == 4

        return 0

    monkeypatch.setattr(
        cli,
        "_execute_validated",
        operation,
    )

    assert cli.main(["--source", "bayt"]) == 0


def test_recovery_bypasses_collection_lock(monkeypatch):

    operation = Mock(return_value=0)

    monkeypatch.setattr(
        cli,
        "_execute_validated",
        operation,
    )

    guard = Mock(
        side_effect=AssertionError("Unexpected source lock")
    )

    monkeypatch.setattr(
        guarded_cli,
        "execute_guarded",
        guard,
    )

    assert cli.main([
        "--recover-run-id",
        "11111111-1111-4111-8111-000000000001",
    ]) == 0

    guard.assert_not_called()
    operation.assert_called_once()


def test_publication_gate_runs_under_exclusive_lock():

    manager = FakeManager()
    events = []

    def gate(connection):
        assert manager.active
        events.append("gate")

    def runner(stage, connection):
        assert manager.active
        events.append(stage)
        return 0

    assert module.execute_protected(
        manager,
        runner,
        publication_gate=gate,
    ) == 0

    assert events == ["gate", "seed", "run", "test"]


def test_publication_gate_blocks_all_stages():

    manager = FakeManager()

    def gate(connection):
        assert manager.active
        raise module.PublicationBlockedError("Pending recovery")

    runner = Mock()

    with pytest.raises(module.PublicationBlockedError):
        module.execute_protected(
            manager,
            runner,
            publication_gate=gate,
        )

    runner.assert_not_called()
    assert not manager.active


@pytest.mark.parametrize("blocked", [True, False])
def test_publication_query_contract(blocked):

    connection = Mock()

    connection.execute.return_value.fetchall.return_value = (
        [("run-1", "bayt")] if blocked else []
    )

    if blocked:
        with pytest.raises(module.PublicationBlockedError):
            module.verify_publication_ready(connection)
    else:
        module.verify_publication_ready(connection)

    sql = connection.execute.call_args.args[0]

    assert "r.status = 'running'" in sql

    for table in (
        "ingestion_observations",
        "source_listing_history",
        "source_listings",
        "invalid_records",
    ):
        assert "bronze." + table in sql
