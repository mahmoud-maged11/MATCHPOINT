import json

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest

from scrapers import main as cli
from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)


@pytest.mark.parametrize(
    "source,mode",
    [
        ("wuzzuf", "api"),
        ("forasna", "live"),
        ("egyincs", "api"),
        ("itida", "live"),
        ("nti", "live"),
        ("bayt", "live"),
        ("devpost", "api"),
        ("un_volunteers", "api"),
    ],
)
def test_source_configuration(source, mode):
    parser = cli.build_parser()

    args = parser.parse_args([
        "--source", source,
        "--mode", mode,
    ])

    assert cli.validate_arguments(parser, args) == mode


@pytest.mark.parametrize(
    "arguments",
    [
        ["--source", "invalid"],
        ["--source", "bayt", "--mode", "api"],
        ["--source", "devpost", "--mode", "html"],
        ["--source", "wuzzuf", "--mode", "live"],
        ["--source", "wuzzuf"],
        ["--source", "bayt", "--max-jobs", "0"],
        ["--source", "bayt", "--max-pages", "-1"],
        ["--source", "bayt", "--page-size", "abc"],
        ["--source", "bayt", "--endpoint", "jobs"],
        ["--source", "bayt", "--storage", "both"],
        ["--source", "bayt", "--postgres-db", "test"],
        [
            "--source", "bayt",
            "--storage", "postgres",
            "--output", "result.json",
        ],
    ],
)
def test_invalid_arguments_rejected(arguments):
    parser = cli.build_parser()

    with pytest.raises(SystemExit) as error:
        args = parser.parse_args(arguments)
        cli.validate_arguments(parser, args)

    assert error.value.code == 2


@pytest.mark.parametrize(
    "source",
    cli.SOURCES,
)
def test_scraper_construction(source):
    parser = cli.build_parser()

    args = parser.parse_args([
        "--source", source,
        "--mode", (
            "api"
            if source == "wuzzuf"
            or source in cli.API_SOURCES
            else "live"
        ),
        "--max-jobs", "5",
        "--max-pages", "2",
    ])

    mode = cli.validate_arguments(parser, args)

    scraper = cli.create_scraper(args, mode)

    assert scraper.source_name == source


def test_wuzzuf_offline_html(tmp_path):
    path = tmp_path / "wuzzuf.html"
    path.write_text("<html></html>", encoding="utf-8")

    parser = cli.build_parser()

    args = parser.parse_args([
        "--source", "wuzzuf",
        "--html-path", str(path),
    ])

    assert cli.validate_arguments(parser, args) == "html"

    scraper = cli.create_scraper(args, "html")

    assert scraper.source_name == "wuzzuf"


def make_result(
    status=CollectionStatus.COMPLETED,
    reason=StopReason.REQUESTED_LIMIT,
):
    opportunity = Mock()

    opportunity.model_dump.return_value = {
        "title": "مهندس بيانات",
        "source_name": "devpost",
    }

    return SimpleNamespace(
        status=status,
        stop_reason=reason,
        opportunities=(opportunity,),
        accepted_count=1,
        rejected_count=0,
    )


@pytest.mark.parametrize(
    "status,reason,expected",
    [
        (
            CollectionStatus.COMPLETED,
            StopReason.REQUESTED_LIMIT,
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
def test_json_exit_codes(
    monkeypatch,
    status,
    reason,
    expected,
):
    scraper = Mock()

    scraper.run_with_result.return_value = make_result(
        status,
        reason,
    )

    monkeypatch.setattr(
        cli,
        "create_scraper",
        lambda *args: scraper,
    )

    assert cli.main([
        "--source", "devpost",
    ]) == expected


def test_json_storage_does_not_use_postgres(
    monkeypatch,
    tmp_path,
):
    scraper = Mock()
    scraper.run_with_result.return_value = make_result()

    orchestrator_factory = Mock(
        side_effect=AssertionError(
            "PostgreSQL must not be initialized"
        )
    )

    monkeypatch.setattr(
        cli,
        "create_scraper",
        lambda *args: scraper,
    )

    monkeypatch.setattr(
        cli,
        "create_orchestrator",
        orchestrator_factory,
    )

    output = tmp_path / "output.json"

    result = cli.main([
        "--source", "devpost",
        "--storage", "json",
        "--output", str(output),
    ])

    assert result == 0
    assert output.exists()

    data = json.loads(
        output.read_text(encoding="utf-8")
    )

    assert data[0]["title"] == "مهندس بيانات"

    orchestrator_factory.assert_not_called()


@pytest.mark.parametrize(
    "storage_mode",
    ["postgres", "both"],
)
def test_persistent_execution(
    monkeypatch,
    tmp_path,
    storage_mode,
):
    scraper = Mock()
    scraper.last_result = make_result()

    orchestrator = Mock()

    orchestrator.execute_with_recovery.return_value = SimpleNamespace(
        collection_status=CollectionStatus.COMPLETED,
        stop_reason=StopReason.REQUESTED_LIMIT,
        finalized_run={
            "records_received": 1,
            "records_inserted": 1,
        },
    )

    monkeypatch.setattr(
        cli,
        "create_scraper",
        lambda *args: scraper,
    )

    monkeypatch.setattr(
        cli,
        "create_orchestrator",
        lambda *args: orchestrator,
    )

    arguments = [
        "--source", "devpost",
        "--storage", storage_mode,
    ]

    output = tmp_path / "output.json"

    if storage_mode == "both":
        arguments.extend([
            "--output", str(output),
        ])

    assert cli.main(arguments) == 0

    orchestrator.execute_with_recovery.assert_called_once()

    kwargs = orchestrator.execute_with_recovery.call_args.kwargs

    assert kwargs["scraper"] is scraper
    assert kwargs["collection_mode"] == "api"
    assert kwargs["collection_scope"] == "default"
    assert isinstance(kwargs["run_id"], UUID)

    scraper.run_with_result.assert_not_called()

    assert output.exists() == (storage_mode == "both")


def test_database_failure_prevents_collection(monkeypatch):
    scraper_factory = Mock()

    monkeypatch.setattr(
        cli,
        "create_scraper",
        scraper_factory,
    )

    monkeypatch.setattr(
        cli,
        "create_orchestrator",
        Mock(side_effect=ConnectionError("secret")),
    )

    assert cli.main([
        "--source", "devpost",
        "--storage", "postgres",
    ]) == 1

    scraper_factory.assert_not_called()


def test_sensitive_error_not_printed(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "create_scraper",
        Mock(
            side_effect=RuntimeError(
                "sensitive-password-123"
            )
        ),
    )

    assert cli.main([
        "--source", "devpost",
    ]) == 1

    captured = capsys.readouterr()

    assert "sensitive-password-123" not in captured.err
    assert "RuntimeError" in captured.err
    assert "Run ID:" in captured.err


def test_keyboard_interrupt(monkeypatch):
    scraper = Mock()

    scraper.run_with_result.side_effect = KeyboardInterrupt

    monkeypatch.setattr(
        cli,
        "create_scraper",
        lambda *args: scraper,
    )

    assert cli.main([
        "--source", "devpost",
    ]) == 130


def test_atomic_json_preserves_previous_file(tmp_path):
    output = tmp_path / "result.json"

    output.write_text(
        '{"previous": true}',
        encoding="utf-8",
    )

    opportunity = Mock()

    opportunity.model_dump.return_value = {
        "invalid": float("nan"),
    }

    with pytest.raises(ValueError):
        cli.write_json_atomic(
            output,
            [opportunity],
        )

    assert json.loads(
        output.read_text(encoding="utf-8")
    ) == {"previous": True}

    assert list(tmp_path.iterdir()) == [output]


def test_atomic_json_replaces_previous_file(tmp_path):
    output = tmp_path / "result.json"

    output.write_text("[]", encoding="utf-8")

    result = make_result()

    cli.write_json_atomic(
        output,
        result.opportunities,
    )

    data = json.loads(
        output.read_text(encoding="utf-8")
    )

    assert len(data) == 1
    assert data[0]["title"] == "مهندس بيانات"
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("storage_mode", ["json", "both"])
def test_export_failure_reported_separately(
    monkeypatch,
    tmp_path,
    capsys,
    storage_mode,
):
    scraper = Mock()
    scraper.last_result = make_result()
    scraper.run_with_result.return_value = scraper.last_result

    orchestrator = Mock()

    orchestrator.execute_with_recovery.return_value = SimpleNamespace(
        collection_status=CollectionStatus.COMPLETED,
        stop_reason=StopReason.REQUESTED_LIMIT,
        finalized_run={
            "records_received": 1,
            "records_inserted": 1,
        },
    )

    monkeypatch.setattr(
        cli, "create_scraper", lambda *args: scraper
    )

    monkeypatch.setattr(
        cli, "create_orchestrator", lambda *args: orchestrator
    )

    monkeypatch.setattr(
        cli,
        "write_json_atomic",
        Mock(side_effect=OSError("private path")),
    )

    result = cli.main([
        "--source", "devpost",
        "--storage", storage_mode,
        "--output", str(tmp_path / "result.json"),
    ])

    assert result == 3

    captured = capsys.readouterr()
    summary = json.loads(captured.out)

    assert summary["status"] == "completed"
    assert summary["export_status"] == "failed"

    assert summary["persistence_status"] == (
        "finalized" if storage_mode == "both"
        else "not_requested"
    )

    assert "private path" not in captured.err

    if storage_mode == "both":
        orchestrator.execute_with_recovery.assert_called_once()
    else:
        orchestrator.execute_with_recovery.assert_not_called()


def test_successful_export_summary(
    monkeypatch,
    tmp_path,
    capsys,
):
    scraper = Mock()
    scraper.run_with_result.return_value = make_result()

    monkeypatch.setattr(
        cli, "create_scraper", lambda *args: scraper
    )

    assert cli.main([
        "--source", "devpost",
        "--output", str(tmp_path / "result.json"),
    ]) == 0

    summary = json.loads(capsys.readouterr().out)

    assert summary["export_status"] == "completed"
    assert summary["persistence_status"] == "not_requested"
    assert summary["export_scope"] == "collected_opportunities"


def test_partial_collection_preserves_exit_code(
    monkeypatch,
    tmp_path,
    capsys,
):
    scraper = Mock()

    scraper.run_with_result.return_value = make_result(
        CollectionStatus.PARTIAL,
        StopReason.SOURCE_ERROR,
    )

    monkeypatch.setattr(
        cli, "create_scraper", lambda *args: scraper
    )

    monkeypatch.setattr(
        cli,
        "write_json_atomic",
        Mock(side_effect=OSError("Export failed")),
    )

    assert cli.main([
        "--source", "devpost",
        "--output", str(tmp_path / "result.json"),
    ]) == 2

    summary = json.loads(capsys.readouterr().out)

    assert summary["status"] == "partial"
    assert summary["export_status"] == "failed"
