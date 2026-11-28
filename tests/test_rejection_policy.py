
from uuid import uuid4

import pytest

from scrapers.storage.rejection_policy import (
    RejectionPolicy,
)

from scrapers.utils.invalid_records import (
    InvalidRecord,
)


@pytest.fixture
def policy():

    return RejectionPolicy(b"x" * 32)


def make_record(
    source="wuzzuf",
    payload=None,
    error_type="ValueError",
):

    return InvalidRecord(
        run_id=str(uuid4()),
        source_name=source,
        source_url=(
            "https://example.com/job"
            "?token=synthetic-secret"
        ),
        raw_payload=payload or {},
        error_type=error_type,
        error_message=(
            "Private email: synthetic@example.com"
        ),
    )


@pytest.mark.parametrize(
    "source,payload,expected",
    [
        (
            "wuzzuf",
            {"api_id": "AbC123"},
            "AbC123",
        ),
        (
            "forasna",
            {"source_id": "123"},
            "123",
        ),
        (
            "egyincs",
            {"id": 123, "endpoint": "jobs"},
            "123",
        ),
        (
            "itida",
            {
                "page_type": "program",
                "slug": "AI-Training",
            },
            "program:ai-training",
        ),
        (
            "nti",
            {
                "initiative": "hire_ready",
                "track_id": 123,
            },
            "hire_ready:123",
        ),
        (
            "nti",
            {
                "initiative": "creativa",
                "track_id": 123,
                "center_id": 45,
            },
            "creativa:123:center:45",
        ),
        (
            "bayt",
            {"job_id": 123},
            "123",
        ),
        (
            "devpost",
            {"id": 123, "open_state": "open"},
            "123",
        ),
        (
            "un_volunteers",
            {"assignment_id": 123},
            "123",
        ),
    ],
)
def test_source_identity(
    policy, source, payload, expected
):

    result = policy.sanitize(
        make_record(source, payload)
    )

    assert result.source_opportunity_id == expected


@pytest.mark.parametrize(
    "source",
    [
        "wuzzuf",
        "forasna",
        "egyincs",
        "itida",
        "nti",
        "bayt",
        "devpost",
        "un_volunteers",
    ],
)
def test_private_payload_removed(policy, source):

    record = make_record(
        source,
        {
            "card_html": "<p>synthetic-secret</p>",
            "email": "synthetic@example.com",
            "token": "synthetic-secret",
            "nested": {
                "password": "synthetic-secret",
            },
        },
    )

    result = policy.sanitize(record)

    assert result.source_url is None

    assert set(result.record_payload) == {
        "policy_version",
        "evidence_fingerprint",
    }

    assert "synthetic-secret" not in repr(result)
    assert "synthetic@example.com" not in repr(result)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        -1,
        1.5,
        "",
        "abc",
        " 123 ",
        "123@example.com",
        {"id": 123},
        [123],
    ],
)
def test_invalid_numeric_identity(policy, value):

    result = policy.sanitize(
        make_record(
            "bayt",
            {"job_id": value},
        )
    )

    assert result.source_opportunity_id is None
    assert "job_id" not in result.record_payload


def test_invalid_token_removed(policy):

    result = policy.sanitize(
        make_record(
            "wuzzuf",
            {"api_id": "private@example.com"},
        )
    )

    assert result.source_opportunity_id is None
    assert "api_id" not in result.record_payload


def test_missing_creativa_center(policy):

    result = policy.sanitize(
        make_record(
            "nti",
            {
                "initiative": "creativa",
                "track_id": 123,
            },
        )
    )

    assert result.source_opportunity_id is None


def test_invalid_enum_removed(policy):

    result = policy.sanitize(
        make_record(
            "devpost",
            {
                "id": 123,
                "open_state": ["open"],
            },
        )
    )

    assert "open_state" not in result.record_payload


@pytest.mark.parametrize(
    "error_code,stage",
    [
        ("MissingRequiredField", "extraction"),
        ("ValidationError", "validation"),
        ("SourceIdentityError", "identity"),
        ("ValueError", "mapping"),
        ("TypeError", "mapping"),
    ],
)
def test_failure_classification(
    policy, error_code, stage
):

    result = policy.sanitize(
        make_record(error_type=error_code)
    )

    assert result.failure_stage == stage
    assert result.error_code == error_code


def test_untrusted_error_code_removed(policy):

    result = policy.sanitize(
        make_record(
            error_type="synthetic@example.com"
        )
    )

    assert result.error_code == "ScraperRecordError"


def test_reserved_conflict_code_not_allowed(policy):

    result = policy.sanitize(
        make_record(
            error_type="SameRunObservationMismatch"
        )
    )

    assert result.error_code == "ScraperRecordError"


def test_fingerprint_deterministic(policy):

    first = make_record(
        payload={"a": 1, "b": 2}
    )

    second = make_record(
        payload={"b": 2, "a": 1}
    )

    assert (
        policy.fingerprint(first)
        == policy.fingerprint(second)
    )


def test_distinct_rejected_payloads(policy):

    first = make_record(
        payload={"card_html": "<p>First</p>"}
    )

    second = make_record(
        payload={"card_html": "<p>Second</p>"}
    )

    a = policy.sanitize(first)
    b = policy.sanitize(second)

    assert (
        a.record_payload["evidence_fingerprint"]
        != b.record_payload["evidence_fingerprint"]
    )


def test_fingerprint_ignores_collection_time(policy):

    record = make_record()

    copied = record.model_copy(
        update={"run_id": str(uuid4())}
    )

    assert (
        policy.fingerprint(record)
        == policy.fingerprint(copied)
    )


def test_fingerprint_depends_on_key(policy):

    record = make_record()

    other = RejectionPolicy(b"y" * 32)

    assert (
        policy.fingerprint(record)
        != other.fingerprint(record)
    )


def test_short_key_rejected():

    with pytest.raises(ValueError):

        RejectionPolicy(b"short")


def test_invalid_key_type():

    with pytest.raises(TypeError):

        RejectionPolicy("not-bytes")


def test_invalid_record_type(policy):

    with pytest.raises(TypeError):

        policy.sanitize({})


def test_original_record_not_modified(policy):

    record = make_record(
        payload={
            "api_id": "ABC123",
            "private": "synthetic-secret",
        }
    )

    before = record.model_dump()

    policy.sanitize(record)

    assert record.model_dump() == before
