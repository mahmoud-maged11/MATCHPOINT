from dataclasses import replace
from uuid import uuid4

import pytest

from scrapers.collection_result import (
    CollectionResult,
    CollectionStatus,
    StopReason,
)

from scrapers.storage.postgres import (
    PostgresSettings,
)

from scrapers.storage.snapshot_config import (
    create_snapshot_store,
    snapshot_namespace,
)


@pytest.fixture
def settings():

    return PostgresSettings(
        host="127.0.0.1",
        port=5432,
        database="matchpoint",
        user="matchpoint",
        password="test-password",
    )


@pytest.fixture
def snapshot_root(tmp_path, monkeypatch):

    root = tmp_path / "snapshots"

    monkeypatch.setenv(
        "SNAPSHOT_DIRECTORY",
        str(root),
    )

    monkeypatch.setenv(
        "SNAPSHOT_ENCRYPTION_KEY",
        "ab" * 32,
    )

    return root


def test_namespace_is_deterministic(settings):

    assert snapshot_namespace(settings) == (
        snapshot_namespace(settings)
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"database": "matchpoint_test"},
        {"host": "192.168.1.10"},
        {"port": 5433},
    ],
)
def test_different_database_targets_are_isolated(
    settings,
    changes,
):

    other = replace(settings, **changes)

    assert snapshot_namespace(settings) != (
        snapshot_namespace(other)
    )


def test_credentials_do_not_change_namespace(settings):

    other = replace(
        settings,
        user="another_user",
        password="another_password",
    )

    assert snapshot_namespace(settings) == (
        snapshot_namespace(other)
    )


def test_namespace_contains_no_credentials(settings):

    namespace = snapshot_namespace(settings)

    assert settings.password not in namespace


def test_database_name_cannot_escape_directory(
    settings,
    snapshot_root,
):

    other = replace(
        settings,
        database="../../outside",
    )

    store = create_snapshot_store(
        settings=other,
    )

    assert store.directory.parent == (
        snapshot_root.resolve()
    )


def test_legacy_store_remains_compatible(
    snapshot_root,
):

    store = create_snapshot_store()

    assert store.directory == (
        snapshot_root.resolve()
    )


def test_same_database_reuses_directory(
    settings,
    snapshot_root,
):

    first = create_snapshot_store(
        settings=settings,
    )

    second = create_snapshot_store(
        settings=settings,
    )

    assert first.directory == second.directory


def test_separate_databases_cannot_see_snapshots(
    settings,
    snapshot_root,
):

    production = create_snapshot_store(
        settings=settings,
    )

    testing = create_snapshot_store(
        settings=replace(
            settings,
            database="matchpoint_test",
        ),
    )

    run_id = uuid4()

    result = CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        status=CollectionStatus.COMPLETED,
        stop_reason=StopReason.INPUT_EXHAUSTED,
    )

    production.save(result)

    assert production.exists(run_id)
    assert not testing.exists(run_id)

    assert production.directory != testing.directory


def test_legacy_snapshots_are_not_moved(
    settings,
    snapshot_root,
):

    legacy = create_snapshot_store()

    run_id = uuid4()

    result = CollectionResult(
        run_id=run_id,
        source_name="wuzzuf",
        status=CollectionStatus.COMPLETED,
        stop_reason=StopReason.INPUT_EXHAUSTED,
    )

    original = legacy.save(result)

    before = original.read_bytes()

    isolated = create_snapshot_store(
        settings=settings,
    )

    assert original.exists()
    assert original.read_bytes() == before
    assert not isolated.exists(run_id)
