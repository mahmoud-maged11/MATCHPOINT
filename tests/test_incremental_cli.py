import json

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from scrapers import main as cli

from test_full_load_integration import parse


BASE = (
    "--source", "egyincs",
    "--storage", "postgres",
    "--load-strategy", "incremental",
    "--endpoint", "jobs",
)

NOW = datetime(
    2026, 11, 27, 12, 0,
    tzinfo=timezone.utc,
)


@pytest.mark.parametrize(
    "endpoint",
    ["jobs", "lp_course"],
)
def test_incremental_defaults(endpoint):

    args, mode = parse(
        *BASE[:-1], endpoint
    )

    assert mode == "api"
    assert args.max_jobs is None
    assert args.max_pages is None
    assert args.page_size == 20
    assert not args.bootstrap


@pytest.mark.parametrize(
    "arguments",
    [
        (
            "--source", "egyincs",
            "--load-strategy", "incremental",
            "--endpoint", "jobs",
        ),
        (
            "--source", "egyincs",
            "--storage", "postgres",
            "--load-strategy", "incremental",
        ),
        (*BASE[:-1], "all"),
        (*BASE, "--mode", "html"),
        (*BASE, "--page-size", "21"),
        ("--source", "egyincs", "--bootstrap"),
        (
            "--source", "egyincs",
            "--load-strategy", "full",
            "--bootstrap",
        ),
        (
            "--recover-run-id",
            "11111111-1111-4111-8111-000000000001",
            "--bootstrap",
        ),
        (
            "--source", "devpost",
            "--storage", "postgres",
            "--load-strategy", "incremental",
        ),
    ],
)
def test_invalid_incremental_arguments(arguments):

    with pytest.raises(SystemExit) as error:

        parse(*arguments)

    assert error.value.code == 2


def test_explicit_incremental_limits():

    args, _ = parse(
        *BASE,
        "--max-jobs", "100",
        "--max-pages", "5",
    )

    assert args.max_jobs == 100
    assert args.max_pages == 5


@pytest.fixture
def repository(monkeypatch):

    from scrapers.storage import checkpoints

    repository = Mock()

    monkeypatch.setattr(
        checkpoints,
        "CheckpointRepository",
        Mock(return_value=repository),
    )

    return repository


def build(repository, *, bootstrap=False, current=None):

    repository.get_checkpoint.return_value = current

    args, mode = parse(
        *BASE,
        *(("--bootstrap",) if bootstrap else ()),
    )

    run_id = uuid4()

    orchestrator = SimpleNamespace(
        storage=Mock(),
    )

    intent = cli.build_checkpoint_intent(
        args,
        orchestrator,
        run_id,
        now=NOW,
    )

    return args, mode, intent


def existing_checkpoint():

    return {
        "checkpoint_type": "timestamp",
        "checkpoint_value": {
            "timestamp": (
                NOW - timedelta(hours=1)
            ).isoformat(),
        },
        "last_successful_run_id": uuid4(),
    }


def test_bootstrap_requires_explicit_permission(repository):

    with pytest.raises(
        ValueError,
        match="explicit bootstrap",
    ):

        build(repository)


def test_bootstrap_uses_historical_watermark(repository):

    args, mode, intent = build(
        repository,
        bootstrap=True,
    )

    assert intent.previous_run_id is None

    assert intent.previous_watermark == datetime(
        1970, 1, 1,
        tzinfo=timezone.utc,
    )

    assert intent.window.lower == (
        intent.previous_watermark
        - timedelta(minutes=5)
    )

    assert intent.target_watermark == (
        NOW - timedelta(minutes=2)
    )

    scraper = cli.create_scraper(
        args,
        mode,
        incremental_window=intent.window,
    )

    assert scraper.incremental_window == intent.window
    assert scraper.endpoint == "jobs"


def test_resume_existing_checkpoint(repository):

    current = existing_checkpoint()

    _, _, intent = build(
        repository,
        current=current,
    )

    assert intent.previous_run_id == (
        current["last_successful_run_id"]
    )

    assert intent.previous_watermark == (
        NOW - timedelta(hours=1)
    )

    repository.get_checkpoint.assert_called_once_with(
        source_name="egyincs",
        collection_scope="jobs",
    )


def test_bootstrap_cannot_replace_checkpoint(repository):

    with pytest.raises(
        ValueError,
        match="cannot replace",
    ):

        build(
            repository,
            bootstrap=True,
            current=existing_checkpoint(),
        )


def test_incompatible_checkpoint_type(repository):

    current = existing_checkpoint()
    current["checkpoint_type"] = "numeric_id"

    with pytest.raises(
        ValueError,
        match="timestamp checkpoint",
    ):

        build(repository, current=current)


def test_missing_incremental_window_rejected():

    args, mode = parse(*BASE)

    with pytest.raises(
        ValueError,
        match="fixed window",
    ):

        cli.create_scraper(args, mode)


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("advanced", 0),
        ("not_advanced", 2),
        ("skipped_unsafe_counters", 2),
        ("skipped_checkpoint_conflict", 2),
    ],
)
def test_checkpoint_exit_codes(outcome, expected):

    assert cli.collection_exit_code(
        "completed",
        {"outcome": outcome},
    ) == expected


@pytest.mark.parametrize(
    "status,expected",
    [
        ("completed", 0),
        ("partial", 2),
        ("failed", 1),
        ("aborted", 130),
    ],
)
def test_legacy_exit_codes(status, expected):

    assert cli.collection_exit_code(
        status
    ) == expected


def test_checkpoint_summary():

    assert cli.checkpoint_summary({}) is None

    row = {
        "metadata": {
            "checkpoint_intent": {},
        },
    }

    assert cli.checkpoint_summary(row) == {
        "outcome": "not_advanced",
    }

    receipt = {
        "version": 1,
        "outcome": "advanced",
    }

    row["metadata"]["checkpoint_finalization"] = receipt

    assert cli.checkpoint_summary(row) == receipt


def test_cli_execution_wires_intent(
    repository,
    monkeypatch,
    capsys,
):

    repository.get_checkpoint.return_value = (
        existing_checkpoint()
    )

    from scrapers.collection_result import (
        CollectionStatus,
        StopReason,
    )

    orchestrator = Mock()
    scraper = Mock()

    scraper.last_result = SimpleNamespace(
        opportunities=(),
        accepted_count=0,
        rejected_count=0,
    )

    orchestrator.execute_with_recovery.return_value = SimpleNamespace(
        collection_status=CollectionStatus.COMPLETED,
        stop_reason=StopReason.SOURCE_EXHAUSTED,
        finalized_run={
            "metadata": {
                "checkpoint_intent": {},
                "checkpoint_finalization": {
                    "outcome": "advanced",
                },
            },
        },
    )

    monkeypatch.setattr(
        cli,
        "create_orchestrator",
        Mock(return_value=orchestrator),
    )

    monkeypatch.setattr(
        cli,
        "create_scraper",
        Mock(return_value=scraper),
    )

    assert cli.main(list(BASE)) == 0

    arguments = orchestrator.execute_with_recovery.call_args.kwargs

    intent = arguments["checkpoint_intent"]

    assert arguments["run_id"] == intent.run_id
    assert arguments["collection_scope"] == "jobs"

    assert cli.create_scraper.call_args.kwargs[
        "incremental_window"
    ] == intent.window

    summary = json.loads(
        capsys.readouterr().out
    )

    assert summary["checkpoint"]["outcome"] == "advanced"
