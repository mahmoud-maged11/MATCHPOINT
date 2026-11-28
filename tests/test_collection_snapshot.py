import json

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from scrapers.sources.wuzzuf import WuzzufScraper

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from scrapers.storage.collection_snapshot import (
    CollectionSnapshotStore,
    SnapshotError,
    SnapshotIntegrityError,
    SnapshotConflictError,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "wuzzuf_synthetic.html"
)

TEST_KEY = b"x" * 32


@pytest.fixture
def store(tmp_path):
    return CollectionSnapshotStore(
        tmp_path / "snapshots",
        integrity_key=TEST_KEY,
    )


@pytest.fixture
def collection():
    scraper = WuzzufScraper(
        html_path=str(FIXTURE)
    )

    result = scraper.run_with_result(
        run_id=uuid4()
    )

    assert result.accepted_count == 3
    assert result.rejected_count == 2

    return result


def test_snapshot_full_roundtrip(store, collection):

    store.save(collection)

    restored = store.load(collection.run_id)

    assert restored == collection
    assert restored.accepted_count == 3
    assert restored.rejected_count == 2
    assert restored.status == CollectionStatus.COMPLETED
    assert restored.stop_reason == StopReason.INPUT_EXHAUSTED


def test_snapshot_preserves_opportunities(store, collection):

    store.save(collection)

    restored = store.load(collection.run_id)

    for original, recovered in zip(
        collection.opportunities,
        restored.opportunities,
        strict=True,
    ):
        assert original.model_dump(mode="json") == (
            recovered.model_dump(mode="json")
        )

        assert original.collected_at == recovered.collected_at
        assert original.raw_payload == recovered.raw_payload


def test_snapshot_preserves_rejections(store, collection):

    store.save(collection)

    restored = store.load(collection.run_id)

    for original, recovered in zip(
        collection.invalid_records,
        restored.invalid_records,
        strict=True,
    ):
        assert original.model_dump(mode="json") == (
            recovered.model_dump(mode="json")
        )

        assert original.collected_at == recovered.collected_at
        assert original.run_id == recovered.run_id
        assert original.raw_payload == recovered.raw_payload


def test_snapshot_survives_new_store_instance(
    store,
    collection,
):
    store.save(collection)

    restarted_store = CollectionSnapshotStore(
        store.directory,
        integrity_key=TEST_KEY,
    )

    assert restarted_store.load(
        collection.run_id
    ) == collection


def test_missing_snapshot(store):

    run_id = uuid4()

    assert not store.exists(run_id)

    with pytest.raises(SnapshotError):
        store.load(run_id)


def test_idempotent_save(store, collection):

    path = store.save(collection)

    original = path.read_bytes()
    modified_at = path.stat().st_mtime_ns

    assert store.save(collection) == path

    assert path.read_bytes() == original
    assert path.stat().st_mtime_ns == modified_at


def test_conflicting_snapshot(store, collection):

    path = store.save(collection)

    original = path.read_bytes()

    changed = replace(
        collection,
        status=CollectionStatus.PARTIAL,
        stop_reason=StopReason.SOURCE_ERROR,
    )

    with pytest.raises(SnapshotConflictError):
        store.save(changed)

    assert path.read_bytes() == original
    assert store.load(collection.run_id) == collection


def test_wrong_integrity_key(store, collection):

    store.save(collection)

    wrong_store = CollectionSnapshotStore(
        store.directory,
        integrity_key=b"y" * 32,
    )

    with pytest.raises(SnapshotIntegrityError):
        wrong_store.load(collection.run_id)


@pytest.mark.parametrize(
    "key",
    [
        b"",
        b"x" * 31,
        "not-bytes",
        None,
    ],
)
def test_invalid_integrity_key(tmp_path, key):

    with pytest.raises((TypeError, ValueError)):
        CollectionSnapshotStore(
            tmp_path,
            integrity_key=key,
        )


@pytest.mark.parametrize(
    "run_id",
    [
        "../outside",
        "invalid",
        None,
        123,
    ],
)
def test_invalid_run_id(store, run_id):

    with pytest.raises(TypeError):
        store.load(run_id)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_name", "devpost"),
        ("status", "failed"),
        ("snapshot_version", 999),
        ("contract_version", "999.0.0"),
        ("opportunities", []),
        ("invalid_records", []),
    ],
)
def test_tampered_payload(
    store,
    collection,
    field,
    value,
):
    path = store.save(collection)

    envelope = store._decrypt(
        path.read_bytes()
    )

    envelope["payload"][field] = value

    from scrapers.storage.collection_snapshot import canonical_json

    encrypted = store._cipher.encrypt(
        canonical_json(envelope)
    )

    path.write_bytes(
        canonical_json({
            "encryption_version": 1,
            "ciphertext": encrypted.decode("ascii"),
        })
    )

    with pytest.raises(SnapshotIntegrityError):
        store.load(collection.run_id)


@pytest.mark.parametrize(
    "field,value",
    [
        ("snapshot_version", 999),
        ("contract_version", "999.0.0"),
        ("run_id", str(uuid4())),
    ],
)
def test_signed_incompatible_snapshot(
    store,
    collection,
    field,
    value,
):
    path = store.save(collection)

    envelope = store._decrypt(
        path.read_bytes()
    )

    envelope["payload"][field] = value

    envelope["signature"] = store._signature(
        envelope["payload"]
    )

    from scrapers.storage.collection_snapshot import canonical_json

    encrypted = store._cipher.encrypt(
        canonical_json(envelope)
    )

    path.write_bytes(
        canonical_json({
            "encryption_version": 1,
            "ciphertext": encrypted.decode("ascii"),
        })
    )

    with pytest.raises(SnapshotIntegrityError):
        store.load(collection.run_id)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"{",
        b"null",
        b"[]",
        b'{"payload": {}}',
        b'{"payload": {}, "signature": 123}',
    ],
)
def test_corrupted_snapshot(
    store,
    collection,
    content,
):
    path = store.save(collection)

    path.write_bytes(content)

    with pytest.raises(SnapshotIntegrityError):
        store.load(collection.run_id)


def test_snapshot_cannot_be_used_for_another_run(
    store,
    collection,
):
    path = store.save(collection)

    another_run_id = uuid4()

    another_path = (
        store.directory
        / f"{another_run_id}.json"
    )

    another_path.write_bytes(
        path.read_bytes()
    )

    with pytest.raises(SnapshotIntegrityError):
        store.load(another_run_id)


def test_concurrent_identical_saves(
    store,
    collection,
):
    with ThreadPoolExecutor(max_workers=4) as executor:

        paths = list(
            executor.map(
                store.save,
                [collection] * 8,
            )
        )

    assert len(set(paths)) == 1

    assert store.load(collection.run_id) == collection

    assert len(
        list(store.directory.iterdir())
    ) == 1


def test_concurrent_conflicting_saves(
    store,
    collection,
):
    changed = replace(
        collection,
        status=CollectionStatus.PARTIAL,
        stop_reason=StopReason.SOURCE_ERROR,
    )

    def save(result):
        try:
            store.save(result)
            return "saved"
        except SnapshotConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:

        outcomes = list(
            executor.map(
                save,
                [collection, changed],
            )
        )

    assert sorted(outcomes) == [
        "conflict",
        "saved",
    ]

    assert store.load(collection.run_id) in (
        collection,
        changed,
    )

    assert len(
        list(store.directory.iterdir())
    ) == 1


def test_failed_write_leaves_no_snapshot(
    store,
    collection,
    monkeypatch,
):
    def fail_link(*args, **kwargs):
        raise OSError("Simulated filesystem failure")

    monkeypatch.setattr(
        "scrapers.storage.collection_snapshot.os.link",
        fail_link,
    )

    with pytest.raises(OSError):
        store.save(collection)

    assert not store.exists(collection.run_id)

    assert list(
        store.directory.iterdir()
    ) == []


def test_no_temporary_files_after_conflict(
    store,
    collection,
):
    path = store.save(collection)

    changed = replace(
        collection,
        status=CollectionStatus.PARTIAL,
        stop_reason=StopReason.SOURCE_ERROR,
    )

    with pytest.raises(SnapshotConflictError):
        store.save(changed)

    assert list(
        store.directory.iterdir()
    ) == [path]

def test_encrypted_snapshot_has_no_plaintext(
    store,
    collection,
):
    path = store.save(collection)
    content = path.read_bytes()

    envelope = json.loads(content)

    assert set(envelope) == {
        "encryption_version",
        "ciphertext",
    }

    assert envelope["encryption_version"] == 1

    for value in [
        b"Data Engineer",
        b"raw_payload",
        b"invalid_records",
        str(collection.run_id).encode(),
    ]:
        assert value not in content


def test_ciphertext_tampering(store, collection):

    path = store.save(collection)
    envelope = json.loads(path.read_bytes())

    ciphertext = envelope["ciphertext"]
    position = len(ciphertext) // 2

    replacement = (
        "A" if ciphertext[position] != "A" else "B"
    )

    envelope["ciphertext"] = (
        ciphertext[:position]
        + replacement
        + ciphertext[position + 1:]
    )

    path.write_text(
        json.dumps(envelope),
        encoding="utf-8",
    )

    with pytest.raises(SnapshotIntegrityError):
        store.load(collection.run_id)


@pytest.mark.parametrize(
    "version",
    [0, 2, 999, True, "1", None],
)
def test_unsupported_encryption_version(
    store,
    collection,
    version,
):
    path = store.save(collection)

    envelope = json.loads(path.read_bytes())
    envelope["encryption_version"] = version

    path.write_text(
        json.dumps(envelope),
        encoding="utf-8",
    )

    with pytest.raises(SnapshotIntegrityError):
        store.load(collection.run_id)


def test_plaintext_v1_snapshot_rejected(
    store,
    collection,
):
    path = store.save(collection)

    payload = store._serialize(collection)
    payload["snapshot_version"] = 1

    path.write_text(
        json.dumps({
            "payload": payload,
            "signature": store._signature(payload),
        }),
        encoding="utf-8",
    )

    with pytest.raises(SnapshotIntegrityError):
        store.load(collection.run_id)


def test_encryption_is_randomized(store, collection):

    payload = store._serialize(collection)

    first = store._encrypt(payload)
    second = store._encrypt(payload)

    assert first != second

    assert store._decrypt(first) == (
        store._decrypt(second)
    )


def test_encrypted_snapshot_preserves_original_hashes(
    store,
    collection,
):
    from scrapers.utils.hashing import (
        generate_observation_hash,
    )

    store.save(collection)
    restored = store.load(collection.run_id)

    for original, recovered in zip(
        collection.opportunities,
        restored.opportunities,
        strict=True,
    ):
        assert generate_observation_hash(original) == (
            generate_observation_hash(recovered)
        )
