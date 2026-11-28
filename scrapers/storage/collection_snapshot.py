import base64
import hashlib
import hmac
import json
import os
import tempfile

from pathlib import Path
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from scrapers.collection_result import (
    CollectionResult,
    CollectionStatus,
    StopReason,
)

from scrapers.models import Opportunity
from scrapers.utils.invalid_records import InvalidRecord


SNAPSHOT_VERSION = 2
CONTRACT_VERSION = "3.0.0"
ENCRYPTION_VERSION = 1


class SnapshotError(RuntimeError):
    pass


class SnapshotNotFoundError(SnapshotError):
    pass


class SnapshotIntegrityError(SnapshotError):
    pass


class SnapshotConflictError(SnapshotError):
    pass


def canonical_json(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


class CollectionSnapshotStore:

    def __init__(
        self,
        directory: Path,
        *,
        integrity_key: bytes,
    ):
        if not isinstance(integrity_key, bytes):
            raise TypeError("Integrity key must be bytes")

        if len(integrity_key) < 32:
            raise ValueError(
                "Integrity key must contain at least 32 bytes"
            )

        self.directory = Path(directory).resolve()

        signing_key = hmac.new(
            integrity_key,
            b"matchpoint:snapshot:signing:v2",
            hashlib.sha256,
        ).digest()

        encryption_key = hmac.new(
            integrity_key,
            b"matchpoint:snapshot:encryption:v2",
            hashlib.sha256,
        ).digest()

        self._integrity_key = signing_key

        self._cipher = Fernet(
            base64.urlsafe_b64encode(encryption_key)
        )

    def _path(self, run_id: UUID) -> Path:

        if not isinstance(run_id, UUID):
            raise TypeError("Run ID must be UUID")

        return self.directory / f"{run_id}.json"

    def _signature(self, payload: dict) -> str:

        return hmac.new(
            self._integrity_key,
            b"matchpoint:collection-snapshot:v2|"
            + canonical_json(payload),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _serialize(result: CollectionResult) -> dict:

        if not isinstance(result, CollectionResult):
            raise TypeError("Expected CollectionResult")

        return {
            "snapshot_version": SNAPSHOT_VERSION,
            "contract_version": CONTRACT_VERSION,
            "run_id": str(result.run_id),
            "source_name": result.source_name,
            "status": result.status.value,
            "stop_reason": result.stop_reason.value,
            "opportunities": [
                item.model_dump(mode="json")
                for item in result.opportunities
            ],
            "invalid_records": [
                item.model_dump(mode="json")
                for item in result.invalid_records
            ],
        }

    def _encrypt(self, payload: dict) -> bytes:

        envelope = {
            "payload": payload,
            "signature": self._signature(payload),
        }

        encrypted = self._cipher.encrypt(
            canonical_json(envelope)
        )

        return canonical_json({
            "encryption_version": ENCRYPTION_VERSION,
            "ciphertext": encrypted.decode("ascii"),
        })

    def _decrypt(self, content: bytes) -> dict:

        try:
            encrypted = json.loads(content)

            if not isinstance(encrypted, dict):
                raise SnapshotIntegrityError(
                    "Invalid encrypted snapshot"
                )

            if set(encrypted) != {
                "encryption_version",
                "ciphertext",
            }:
                raise SnapshotIntegrityError(
                    "Invalid encryption envelope"
                )

            if (
                type(encrypted["encryption_version"]) is not int
                or encrypted["encryption_version"]
                != ENCRYPTION_VERSION
            ):
                raise SnapshotIntegrityError(
                    "Unsupported encryption version"
                )

            ciphertext = encrypted["ciphertext"]

            if not isinstance(ciphertext, str):
                raise SnapshotIntegrityError(
                    "Invalid encrypted content"
                )

            decrypted = self._cipher.decrypt(
                ciphertext.encode("ascii")
            )

            envelope = json.loads(decrypted)

            if not isinstance(envelope, dict):
                raise SnapshotIntegrityError(
                    "Invalid snapshot envelope"
                )

            return envelope

        except SnapshotIntegrityError:
            raise

        except InvalidToken:
            raise SnapshotIntegrityError(
                "Snapshot decryption failed"
            ) from None

        except Exception:
            raise SnapshotIntegrityError(
                "Invalid encrypted snapshot"
            ) from None

    def exists(self, run_id: UUID) -> bool:

        return self._path(run_id).is_file()

    def save(self, result: CollectionResult) -> Path:

        payload = self._serialize(result)
        destination = self._path(result.run_id)

        self.directory.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        content = self._encrypt(payload)

        temporary_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.directory,
                prefix=".snapshot-",
                suffix=".tmp",
                delete=False,
            ) as temporary:

                temporary_path = Path(temporary.name)

                temporary.write(content)
                temporary.flush()

                os.fsync(temporary.fileno())

            try:
                os.link(
                    temporary_path,
                    destination,
                )

            except FileExistsError:

                existing = self.load(result.run_id)

                if (
                    canonical_json(self._serialize(existing))
                    != canonical_json(payload)
                ):
                    raise SnapshotConflictError(
                        "Snapshot already exists with different content"
                    )

            if os.name == "posix":

                descriptor = os.open(
                    self.directory,
                    os.O_RDONLY | os.O_DIRECTORY,
                )

                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

            return destination

        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def load(self, run_id: UUID) -> CollectionResult:

        path = self._path(run_id)

        import stat

        try:

            file_stat = path.lstat()

        except FileNotFoundError:

            raise SnapshotNotFoundError(
                "Snapshot does not exist"
            ) from None

        except OSError:

            raise SnapshotError(
                "Snapshot access failed"
            ) from None

        if not stat.S_ISREG(file_stat.st_mode):

            raise SnapshotIntegrityError(
                "Snapshot is not a regular file"
            )

        try:
            envelope = self._decrypt(
                path.read_bytes()
            )

            if set(envelope) != {
                "payload",
                "signature",
            }:
                raise SnapshotIntegrityError(
                    "Invalid snapshot envelope"
                )

            payload = envelope["payload"]
            signature = envelope["signature"]

            if not isinstance(payload, dict):
                raise SnapshotIntegrityError(
                    "Invalid snapshot payload"
                )

            if not isinstance(signature, str):
                raise SnapshotIntegrityError(
                    "Invalid snapshot signature"
                )

            if not hmac.compare_digest(
                signature,
                self._signature(payload),
            ):
                raise SnapshotIntegrityError(
                    "Snapshot integrity verification failed"
                )

            expected_fields = {
                "snapshot_version",
                "contract_version",
                "run_id",
                "source_name",
                "status",
                "stop_reason",
                "opportunities",
                "invalid_records",
            }

            if set(payload) != expected_fields:
                raise SnapshotIntegrityError(
                    "Invalid snapshot fields"
                )

            if (
                type(payload["snapshot_version"]) is not int
                or payload["snapshot_version"]
                != SNAPSHOT_VERSION
            ):
                raise SnapshotIntegrityError(
                    "Unsupported snapshot version"
                )

            if payload["contract_version"] != CONTRACT_VERSION:
                raise SnapshotIntegrityError(
                    "Incompatible data contract"
                )

            if UUID(payload["run_id"]) != run_id:
                raise SnapshotIntegrityError(
                    "Snapshot run identity mismatch"
                )

            if not isinstance(
                payload["opportunities"],
                list,
            ):
                raise SnapshotIntegrityError(
                    "Invalid opportunities collection"
                )

            if not isinstance(
                payload["invalid_records"],
                list,
            ):
                raise SnapshotIntegrityError(
                    "Invalid rejected records collection"
                )

            return CollectionResult(
                run_id=run_id,
                source_name=payload["source_name"],
                status=CollectionStatus(
                    payload["status"]
                ),
                stop_reason=StopReason(
                    payload["stop_reason"]
                ),
                opportunities=tuple(
                    Opportunity.model_validate(item)
                    for item in payload["opportunities"]
                ),
                invalid_records=tuple(
                    InvalidRecord.model_validate(item)
                    for item in payload["invalid_records"]
                ),
            )

        except SnapshotIntegrityError:
            raise

        except Exception:
            raise SnapshotIntegrityError(
                "Invalid or corrupted snapshot"
            ) from None