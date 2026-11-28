import hashlib
import re

from scrapers.checkpoint_intent import CheckpointIntent
from scrapers.collection_result import CollectionResult
from scrapers.incremental_window import PaginationEvidence
from scrapers.storage.collection_snapshot import canonical_json


def result_digest(result):

    if not isinstance(result, CollectionResult):
        raise TypeError("Expected CollectionResult")

    payload = {
        "version": 1,
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

    return hashlib.sha256(
        canonical_json(payload)
    ).hexdigest()


def intent_digest(intent):

    if not isinstance(intent, CheckpointIntent):
        raise TypeError("Expected CheckpointIntent")

    return hashlib.sha256(
        canonical_json(intent.to_metadata())
    ).hexdigest()


def create_coverage_evidence(
    *,
    intent,
    result,
    scraper,
):

    intent.validate_binding(
        run_id=result.run_id,
        source_name=result.source_name,
        collection_scope=scraper.endpoint,
    )

    if scraper.incremental_window != intent.window:
        raise ValueError("Incremental window mismatch")

    if scraper.last_result is not result:
        raise ValueError("Collection result mismatch")

    pagination = scraper.pagination_evidence

    if not isinstance(pagination, PaginationEvidence):
        return None

    if pagination.window != intent.window:
        raise ValueError("Pagination window mismatch")

    if not scraper.incremental_coverage_verified(result):
        return None

    if (
        not pagination.boundary_verified
        or not result.source_exhausted
        or result.rejected_count != 0
        or pagination.expected_total != result.accepted_count
    ):
        return None

    return {
        "version": 1,
        "intent_sha256": intent_digest(intent),
        "result_sha256": result_digest(result),
        "accepted_count": result.accepted_count,
        "pages_seen": pagination.pages_seen,
        "expected_total": pagination.expected_total,
        "expected_pages": pagination.expected_pages,
        "page_size": pagination.page_size,
    }


def validate_coverage_evidence(
    *,
    intent,
    result,
    metadata,
):

    if metadata is None:
        return False

    if not isinstance(metadata, dict):
        raise TypeError("Invalid coverage metadata")

    required = {
        "version",
        "intent_sha256",
        "result_sha256",
        "accepted_count",
        "pages_seen",
        "expected_total",
        "expected_pages",
        "page_size",
    }

    if set(metadata) != required:
        raise ValueError("Invalid coverage fields")

    if (
        type(metadata["version"]) is not int
        or metadata["version"] != 1
    ):
        raise ValueError("Unsupported coverage version")

    for field in (
        "intent_sha256",
        "result_sha256",
    ):

        value = metadata[field]

        if (
            not isinstance(value, str)
            or re.fullmatch("[0-9a-f]{64}", value) is None
        ):
            raise ValueError("Invalid coverage digest")

    for field in (
        "accepted_count",
        "pages_seen",
        "expected_total",
        "expected_pages",
        "page_size",
    ):

        value = metadata[field]

        if type(value) is not int or value < 0:
            raise ValueError("Invalid coverage counter")

    if metadata["page_size"] == 0:
        raise ValueError("Invalid page size")

    intent.validate_binding(
        run_id=result.run_id,
        source_name=result.source_name,
        collection_scope=intent.collection_scope,
    )

    if metadata["intent_sha256"] != intent_digest(intent):
        raise ValueError("Intent digest mismatch")

    if metadata["result_sha256"] != result_digest(result):
        raise ValueError("Result digest mismatch")

    if not result.source_exhausted or result.rejected_count:
        raise ValueError("Unsafe collection result")

    total = metadata["expected_total"]
    page_size = metadata["page_size"]

    expected_pages = (
        total + page_size - 1
    ) // page_size

    if (
        metadata["accepted_count"] != result.accepted_count
        or total != result.accepted_count
        or metadata["expected_pages"] != expected_pages
        or metadata["pages_seen"] != max(1, expected_pages)
    ):
        raise ValueError("Coverage counter mismatch")

    return True
