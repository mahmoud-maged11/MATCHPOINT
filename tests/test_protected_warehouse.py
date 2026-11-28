import importlib.util

from pathlib import Path
from contextlib import contextmanager

import pytest

from scrapers.storage.concurrency import (
    LockUnavailableError,
    LockConnectionLostError,
)


ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "protected_warehouse",
    ROOT / "dbt" / "run_protected.py",
)

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeConnection:

    closed = False
    broken = False

    def execute(self, sql):

        if self.closed:
            raise RuntimeError("Connection closed")

        return self

    def fetchone(self):
        return (1,)


class FakeManager:

    def __init__(self):

        self.active = False
        self.connection = FakeConnection()

    @contextmanager
    def warehouse(self):

        self.active = True

        try:

            yield self.connection

        finally:

            self.active = False


def test_stage_order_and_lock_lifetime():

    manager = FakeManager()
    stages = []

    def runner(stage, connection):

        assert manager.active

        stages.append(stage)

        return 0

    assert module.execute_protected(
        manager, runner
    ) == 0

    assert stages == ["seed", "run", "test"]
    assert not manager.active


@pytest.mark.parametrize(
    "failed_stage,expected",
    [
        ("seed", ["seed"]),
        ("run", ["seed", "run"]),
        ("test", ["seed", "run", "test"]),
    ],
)
def test_failure_stops_pipeline(
    failed_stage,
    expected,
):

    manager = FakeManager()
    stages = []

    def runner(stage, connection):

        stages.append(stage)

        return 2 if stage == failed_stage else 0

    assert module.execute_protected(
        manager, runner
    ) == 2

    assert stages == expected
    assert not manager.active


def test_exception_releases_lock():

    manager = FakeManager()

    def runner(stage, connection):

        raise RuntimeError("Intentional failure")

    with pytest.raises(RuntimeError):

        module.execute_protected(manager, runner)

    assert not manager.active


def test_lock_conflict_prevents_execution():

    class BlockedManager:

        @contextmanager
        def warehouse(self):

            raise LockUnavailableError("Busy")

            yield

    def runner(stage, connection):

        pytest.fail("Runner must not execute")

    with pytest.raises(LockUnavailableError):

        module.execute_protected(
            BlockedManager(),
            runner,
        )


def test_connection_loss_stops_next_stage():

    manager = FakeManager()
    stages = []

    def runner(stage, connection):

        stages.append(stage)

        connection.closed = True

        return 0

    with pytest.raises(LockConnectionLostError):

        module.execute_protected(
            manager, runner
        )

    assert stages == ["seed"]
    assert not manager.active


def test_failed_session_probe():

    class BrokenProbe(FakeConnection):

        def execute(self, sql):

            raise OSError("Network failure")

    with pytest.raises(LockConnectionLostError):

        module.verify_session(BrokenProbe())


def test_closed_connection_detected():

    connection = FakeConnection()
    connection.closed = True

    with pytest.raises(LockConnectionLostError):

        module.verify_session(connection)


def test_lock_lost_before_first_stage():

    manager = FakeManager()
    manager.connection.closed = True

    def runner(stage, connection):

        pytest.fail("Runner must not execute")

    with pytest.raises(LockConnectionLostError):

        module.execute_protected(manager, runner)

    assert not manager.active
