import json

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from scrapers import main as cli

from scrapers.collection_result import (
    CollectionResult,
    CollectionStatus,
    StopReason,
)

from scrapers.storage.orchestrator import (
    IngestionExecutionError,
)


@pytest.fixture
def run_id():

    return uuid4()


@pytest.fixture
def recovery_environment(monkeypatch, run_id):

    result = CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        status=CollectionStatus.COMPLETED,
        stop_reason=StopReason.INPUT_EXHAUSTED,
    )

    execution = SimpleNamespace(
        run_id=run_id,
        collection_status=result.status,
        stop_reason=result.stop_reason,
        collection_result=result,
        already_finalized=False,
        finalized_run={
            "run_id": run_id,
            "source_name": "wuzzuf",
            "status": "completed",
            "records_received": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "records_unchanged": 0,
            "records_invalid": 0,
            "records_stale": 0,
            "records_conflicted": 0,
        },
    )

    orchestrator = Mock()

    orchestrator.recover_with_retry.return_value = execution

    orchestrator.snapshot_store.load.return_value = result

    factory = Mock(return_value=orchestrator)

    scraper_factory = Mock(
        side_effect=AssertionError(
            "Recovery must not create a scraper"
        )
    )

    monkeypatch.setattr(
        cli,
        "create_orchestrator",
        factory,
    )

    monkeypatch.setattr(
        cli,
        "create_scraper",
        scraper_factory,
    )

    return SimpleNamespace(
        orchestrator=orchestrator,
        factory=factory,
        scraper_factory=scraper_factory,
        result=result,
        execution=execution,
    )


def test_recovery_arguments(run_id):

    parser = cli.build_parser()

    args = parser.parse_args([
        "--recover-run-id",
        str(run_id),
    ])

    mode = cli.validate_arguments(
        parser,
        args,
    )

    assert mode == "recovery"
    assert args.recover_run_id == run_id
    assert args.storage == "postgres"
    assert args.source is None


def test_invalid_recovery_uuid():

    with pytest.raises(SystemExit) as error:

        cli.main([
            "--recover-run-id",
            "invalid-uuid",
        ])

    assert error.value.code == 2


def test_source_and_recovery_are_mutually_exclusive(
    run_id,
):

    with pytest.raises(SystemExit) as error:

        cli.main([
            "--source",
            "wuzzuf",
            "--recover-run-id",
            str(run_id),
        ])

    assert error.value.code == 2


@pytest.mark.parametrize(
    "options",
    [
        ["--mode", "api"],
        ["--mode", "html"],
        ["--mode", "live"],
        ["--html-path", "input.html"],
        ["--details-dir", "details"],
        ["--output", "output.json"],
        ["--max-jobs", "20"],
        ["--max-pages", "10"],
        ["--page-size", "20"],
        ["--endpoint", "all"],
        ["--storage", "json"],
        ["--storage", "both"],
    ],
)
def test_collection_options_rejected_during_recovery(
    run_id,
    options,
):

    with pytest.raises(SystemExit) as error:

        cli.main([
            "--recover-run-id",
            str(run_id),
            *options,
        ])

    assert error.value.code == 2


def test_explicit_postgres_storage_allowed(run_id):

    parser = cli.build_parser()

    args = parser.parse_args([
        "--recover-run-id",
        str(run_id),
        "--storage",
        "postgres",
    ])

    assert cli.validate_arguments(
        parser,
        args,
    ) == "recovery"


def test_recovery_preserves_database_options(run_id):

    parser = cli.build_parser()

    args = parser.parse_args([
        "--recover-run-id",
        str(run_id),
        "--postgres-host",
        "127.0.0.1",
        "--postgres-db",
        "matchpoint_cli_test",
    ])

    cli.validate_arguments(parser, args)

    assert args.postgres_host == "127.0.0.1"
    assert args.postgres_db == "matchpoint_cli_test"


def test_successful_recovery(
    run_id,
    recovery_environment,
    capsys,
):

    environment = recovery_environment

    code = cli.main([
        "--recover-run-id",
        str(run_id),
    ])

    assert code == 0

    environment.orchestrator.recover_with_retry.assert_called_once_with(
        run_id=run_id
    )

    environment.scraper_factory.assert_not_called()

    environment.orchestrator.execute_with_recovery.assert_not_called()

    summary = json.loads(
        capsys.readouterr().out
    )

    assert summary["run_id"] == str(run_id)
    assert summary["source"] == "wuzzuf"
    assert summary["operation"] == "recovery"
    assert summary["status"] == "completed"
    assert summary["stop_reason"] == "input_exhausted"
    assert summary["persistence_status"] == "finalized"
    assert summary["export_status"] == "not_requested"
    assert summary["accepted"] == 0
    assert summary["rejected"] == 0

    assert summary["counters"]["records_received"] == 0
    assert summary["already_finalized"] is False

    environment.orchestrator.snapshot_store.load.assert_not_called()


@pytest.mark.parametrize(
    "status,reason,expected_code",
    [
        (
            CollectionStatus.COMPLETED,
            StopReason.INPUT_EXHAUSTED,
            0,
        ),
        (
            CollectionStatus.PARTIAL,
            StopReason.SOURCE_ERROR,
            2,
        ),
        (
            CollectionStatus.FAILED,
            StopReason.SOURCE_ERROR,
            1,
        ),
        (
            CollectionStatus.ABORTED,
            StopReason.INTERRUPTED,
            130,
        ),
    ],
)
def test_recovery_exit_codes(
    run_id,
    recovery_environment,
    capsys,
    status,
    reason,
    expected_code,
):

    environment = recovery_environment

    result = CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        status=status,
        stop_reason=reason,
    )

    environment.orchestrator.snapshot_store.load.return_value = (
        result
    )

    environment.execution.collection_result = result
    environment.execution.collection_status = status
    environment.execution.stop_reason = reason
    environment.execution.finalized_run["status"] = status.value

    code = cli.main([
        "--recover-run-id",
        str(run_id),
    ])

    assert code == expected_code

    summary = json.loads(
        capsys.readouterr().out
    )

    assert summary["status"] == status.value
    assert summary["stop_reason"] == reason.value
    assert summary["persistence_status"] == "finalized"

    environment.scraper_factory.assert_not_called()


def test_recovery_failure_reports_stage(
    run_id,
    recovery_environment,
    capsys,
):

    environment = recovery_environment

    environment.orchestrator.recover_with_retry.side_effect = (
        IngestionExecutionError(
            run_id=run_id,
            stage="snapshot_loading",
        )
    )

    code = cli.main([
        "--recover-run-id",
        str(run_id),
    ])

    assert code == 1

    captured = capsys.readouterr()

    assert "snapshot_loading" in captured.err
    assert str(run_id) in captured.err
    assert captured.out == ""

    environment.scraper_factory.assert_not_called()

    environment.orchestrator.snapshot_store.load.assert_not_called()


def test_recovery_interrupt(
    run_id,
    recovery_environment,
    capsys,
):

    environment = recovery_environment

    environment.orchestrator.recover_with_retry.side_effect = (
        KeyboardInterrupt()
    )

    code = cli.main([
        "--recover-run-id",
        str(run_id),
    ])

    assert code == 130

    captured = capsys.readouterr()

    assert "Recovery interrupted" in captured.err
    assert str(run_id) in captured.err

    environment.scraper_factory.assert_not_called()


def test_configuration_failure_prevents_recovery(
    run_id,
    recovery_environment,
    capsys,
):

    environment = recovery_environment

    environment.factory.side_effect = RuntimeError(
        "sensitive-configuration-value"
    )

    code = cli.main([
        "--recover-run-id",
        str(run_id),
    ])

    assert code == 1

    captured = capsys.readouterr()

    assert "RuntimeError" in captured.err
    assert str(run_id) in captured.err

    assert "sensitive-configuration-value" not in captured.err

    environment.orchestrator.recover_with_retry.assert_not_called()

    environment.scraper_factory.assert_not_called()


def test_recovery_does_not_export_json(
    run_id,
    recovery_environment,
    monkeypatch,
):

    writer = Mock(
        side_effect=AssertionError(
            "Recovery must not export JSON"
        )
    )

    monkeypatch.setattr(
        cli,
        "write_json_atomic",
        writer,
    )

    code = cli.main([
        "--recover-run-id",
        str(run_id),
    ])

    assert code == 0

    writer.assert_not_called()


def test_recovery_does_not_generate_new_run_id(
    run_id,
    recovery_environment,
    monkeypatch,
):

    generator = Mock(
        side_effect=AssertionError(
            "Recovery must preserve the original run ID"
        )
    )

    monkeypatch.setattr(
        cli,
        "uuid4",
        generator,
    )

    code = cli.main([
        "--recover-run-id",
        str(run_id),
    ])

    assert code == 0

    generator.assert_not_called()

    recovery_environment.orchestrator.recover_with_retry.assert_called_once_with(
        run_id=run_id
    )

@pytest.mark.parametrize(
    "status,reason,expected_code",
    [
        (
            CollectionStatus.COMPLETED,
            StopReason.INPUT_EXHAUSTED,
            0,
        ),
        (
            CollectionStatus.PARTIAL,
            StopReason.SOURCE_ERROR,
            2,
        ),
        (
            CollectionStatus.FAILED,
            StopReason.SOURCE_ERROR,
            1,
        ),
        (
            CollectionStatus.ABORTED,
            StopReason.INTERRUPTED,
            130,
        ),
    ],
)
def test_already_finalized_recovery_exit_codes(
    run_id,
    recovery_environment,
    capsys,
    status,
    reason,
    expected_code,
):

    environment = recovery_environment

    result = CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        status=status,
        stop_reason=reason,
    )

    environment.execution.collection_result = result
    environment.execution.collection_status = status
    environment.execution.stop_reason = reason
    environment.execution.already_finalized = True

    environment.execution.finalized_run["status"] = (
        status.value
    )

    environment.orchestrator.snapshot_store.load.side_effect = (
        AssertionError(
            "CLI must not reload the snapshot"
        )
    )

    code = cli.main([
        "--recover-run-id",
        str(run_id),
    ])

    assert code == expected_code

    summary = json.loads(
        capsys.readouterr().out
    )

    assert summary["already_finalized"] is True
    assert summary["status"] == status.value
    assert summary["stop_reason"] == reason.value
    assert summary["persistence_status"] == "finalized"
    assert summary["run_id"] == str(run_id)

    environment.orchestrator.recover_with_retry.assert_called_once_with(
        run_id=run_id
    )

    environment.orchestrator.snapshot_store.load.assert_not_called()

    environment.orchestrator.execute_with_recovery.assert_not_called()

    environment.scraper_factory.assert_not_called()
