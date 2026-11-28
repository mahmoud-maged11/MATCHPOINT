from pathlib import Path

import pytest

from scrapers.storage import snapshot_config

from scrapers.storage.snapshot_config import (
    create_snapshot_store,
    SnapshotConfigurationError,
)


@pytest.fixture(autouse=True)
def configure_environment(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        snapshot_config,
        "BASE_DIR",
        tmp_path,
    )

    monkeypatch.setenv(
        "SNAPSHOT_ENCRYPTION_KEY",
        "ab" * 32,
    )

    monkeypatch.delenv(
        "SNAPSHOT_DIRECTORY",
        raising=False,
    )


def test_default_directory(tmp_path):

    store = create_snapshot_store()

    assert store.directory == (
        tmp_path / ".runtime" / "snapshots"
    ).resolve()

    assert store.directory.is_dir()


def test_relative_directory(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv(
        "SNAPSHOT_DIRECTORY",
        "recovery/snapshots",
    )

    store = create_snapshot_store()

    assert store.directory == (
        tmp_path / "recovery" / "snapshots"
    ).resolve()


def test_absolute_directory(
    monkeypatch,
    tmp_path,
):
    directory = tmp_path / "custom"

    monkeypatch.setenv(
        "SNAPSHOT_DIRECTORY",
        str(directory),
    )

    store = create_snapshot_store()

    assert store.directory == directory.resolve()


def test_working_directory_independence(
    monkeypatch,
    tmp_path,
):
    another_directory = tmp_path / "other"
    another_directory.mkdir()

    monkeypatch.chdir(another_directory)

    store = create_snapshot_store()

    assert store.directory == (
        tmp_path / ".runtime" / "snapshots"
    ).resolve()


def test_missing_encryption_key(monkeypatch):

    monkeypatch.delenv(
        "SNAPSHOT_ENCRYPTION_KEY",
        raising=False,
    )

    with pytest.raises(SnapshotConfigurationError):
        create_snapshot_store()


@pytest.mark.parametrize(
    "key",
    [
        "",
        "abc",
        "ab" * 31,
        "ab" * 33,
        "zz" * 32,
        " " * 64,
    ],
)
def test_invalid_encryption_key(
    monkeypatch,
    key,
):
    monkeypatch.setenv(
        "SNAPSHOT_ENCRYPTION_KEY",
        key,
    )

    with pytest.raises(SnapshotConfigurationError):
        create_snapshot_store()


@pytest.mark.parametrize(
    "directory",
    ["", " ", "   "],
)
def test_empty_directory(
    monkeypatch,
    directory,
):
    monkeypatch.setenv(
        "SNAPSHOT_DIRECTORY",
        directory,
    )

    with pytest.raises(SnapshotConfigurationError):
        create_snapshot_store()


def test_directory_is_existing_file(
    monkeypatch,
    tmp_path,
):
    existing = tmp_path / "existing.txt"

    existing.write_text(
        "test",
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "SNAPSHOT_DIRECTORY",
        str(existing),
    )

    with pytest.raises(SnapshotConfigurationError):
        create_snapshot_store()


def test_configuration_error_does_not_expose_key(
    monkeypatch,
):
    secret = "private-invalid-key"

    monkeypatch.setenv(
        "SNAPSHOT_ENCRYPTION_KEY",
        secret,
    )

    with pytest.raises(
        SnapshotConfigurationError
    ) as error:
        create_snapshot_store()

    assert secret not in str(error.value)