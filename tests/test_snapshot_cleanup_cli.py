import json

from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest

from scrapers import snapshot_cleanup as cli

from scrapers.storage.snapshot_retention import (
    RetentionDecision,
    RetentionResult,
)


@pytest.fixture
def manager(monkeypatch):

    manager = Mock()

    manager.cleanup.return_value = RetentionResult(
        dry_run=True,
        retention_days=30,
        cutoff=datetime.now(timezone.utc),
        decisions=(),
    )

    monkeypatch.setattr(
        cli,
        "create_manager",
        Mock(return_value=manager),
    )

    return manager


def test_default_mode_is_dry_run(manager, capsys):

    assert cli.main([]) == 0

    manager.cleanup.assert_called_once_with(
        dry_run=True
    )

    summary = json.loads(capsys.readouterr().out)

    assert summary["dry_run"] is True
    assert summary["status"] == "completed"
    assert summary["deleted"] == 0


def test_explicit_dry_run(manager):

    assert cli.main(["--dry-run"]) == 0

    manager.cleanup.assert_called_once_with(
        dry_run=True
    )


def test_apply_requires_explicit_flag(manager):

    assert cli.main(["--apply"]) == 0

    manager.cleanup.assert_called_once_with(
        dry_run=False
    )


def test_mutually_exclusive_modes():

    with pytest.raises(SystemExit) as error:

        cli.parse_args([
            "--dry-run",
            "--apply",
        ])

    assert error.value.code == 2


@pytest.mark.parametrize(
    "value",
    ["0", "-1", "abc", "1.5"],
)
def test_invalid_retention_days(value):

    with pytest.raises(SystemExit) as error:

        cli.parse_args([
            "--retention-days",
            value,
        ])

    assert error.value.code == 2


def test_default_retention_days():

    args = cli.parse_args([])

    assert args.retention_days == 30


def test_custom_retention_days():

    args = cli.parse_args([
        "--retention-days",
        "60",
    ])

    assert args.retention_days == 60


def test_database_arguments():

    args = cli.parse_args([
        "--postgres-host",
        "127.0.0.1",
        "--postgres-db",
        "matchpoint_crash_test",
    ])

    assert args.postgres_host == "127.0.0.1"
    assert args.postgres_db == "matchpoint_crash_test"


def test_manager_receives_arguments(manager):

    code = cli.main([
        "--postgres-host",
        "127.0.0.1",
        "--postgres-db",
        "matchpoint_crash_test",
        "--retention-days",
        "60",
    ])

    assert code == 0

    args = cli.create_manager.call_args.args[0]

    assert args.postgres_host == "127.0.0.1"
    assert args.postgres_db == "matchpoint_crash_test"
    assert args.retention_days == 60


def test_cleanup_summary_contains_decisions(
    manager,
    capsys,
):

    run_id = uuid4()

    manager.cleanup.return_value = RetentionResult(
        dry_run=False,
        retention_days=30,
        cutoff=datetime.now(timezone.utc),
        decisions=(
            RetentionDecision(
                run_id=run_id,
                filename=f"{run_id}.json",
                action="deleted",
                reason="retention_period_expired",
                size_bytes=2048,
            ),
        ),
    )

    assert cli.main(["--apply"]) == 0

    summary = json.loads(capsys.readouterr().out)

    assert summary["operation"] == "snapshot_cleanup"
    assert summary["status"] == "completed"
    assert summary["dry_run"] is False
    assert summary["scanned"] == 1
    assert summary["eligible"] == 1
    assert summary["deleted"] == 1
    assert summary["reclaimed_bytes"] == 2048
    assert summary["errors"] == 0

    assert summary["decisions"][0]["run_id"] == str(run_id)
    assert summary["decisions"][0]["action"] == "deleted"


def test_partial_cleanup_exit_code(manager, capsys):

    manager.cleanup.return_value = RetentionResult(
        dry_run=False,
        retention_days=30,
        cutoff=datetime.now(timezone.utc),
        decisions=(
            RetentionDecision(
                run_id=uuid4(),
                filename="test.json",
                action="error",
                reason="PermissionError",
            ),
        ),
    )

    assert cli.main(["--apply"]) == 2

    summary = json.loads(capsys.readouterr().out)

    assert summary["status"] == "partial"
    assert summary["errors"] == 1


def test_initialization_failure(monkeypatch, capsys):

    monkeypatch.setattr(
        cli,
        "create_manager",
        Mock(
            side_effect=RuntimeError(
                "sensitive database details"
            )
        ),
    )

    assert cli.main([]) == 1

    output = capsys.readouterr().out
    summary = json.loads(output)

    assert summary["status"] == "failed"
    assert summary["stage"] == "initialization"
    assert summary["error_type"] == "RuntimeError"
    assert "sensitive database details" not in output


def test_cleanup_failure(manager, capsys):

    manager.cleanup.side_effect = OSError(
        "sensitive filesystem details"
    )

    assert cli.main(["--apply"]) == 1

    output = capsys.readouterr().out
    summary = json.loads(output)

    assert summary["status"] == "failed"
    assert summary["stage"] == "cleanup"
    assert summary["error_type"] == "OSError"
    assert summary["dry_run"] is False
    assert "sensitive filesystem details" not in output


def test_unknown_filename_serialization():

    result = RetentionResult(
        dry_run=True,
        retention_days=30,
        cutoff=datetime.now(timezone.utc),
        decisions=(
            RetentionDecision(
                run_id=None,
                filename="unknown.txt",
                action="skipped",
                reason="unrecognized_filename",
            ),
        ),
    )

    summary = cli.build_summary(result)

    assert summary["skipped"] == 1
    assert summary["decisions"][0]["run_id"] is None
    assert summary["deleted"] == 0
