from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from scrapers.models import Opportunity
from scrapers.storage.identity import (
    SourceIdentity,
    SourceIdentityError,
)
from scrapers.storage import collection_runs
from scrapers.utils.hashing import (
    HASH_VERSION,
    generate_content_hash,
    generate_observation_hash,
)


@pytest.fixture
def opportunity():
    return Opportunity(
        source_name="wuzzuf",
        source_opportunity_id="ABC123",
        source_url="https://wuzzuf.net/jobs/p/ABC123",
        title="Data Engineer",
        organization="MATCHPOINT",
        opportunity_type="job",
        salary_min=Decimal("10000.00"),
        salary_max=Decimal("15000.00"),
        currency="EGP",
        salary_period="monthly",
        required_skills=["Python", "SQL"],
        collected_at=datetime(
            2026, 11, 27, 2, 0,
            tzinfo=timezone.utc,
        ),
        raw_payload={
            "id": "ABC123",
            "items": [1, 2, 3],
        },
    )


def changed(opportunity, **updates):
    return Opportunity.model_validate({
        **opportunity.model_dump(mode="json"),
        **updates,
    })


@pytest.mark.parametrize(
    "source, identifier",
    [
        ("wuzzuf", "AbC123"),
        ("forasna", "12345"),
        ("egyincs", "67890"),
        ("itida", "program:digital-skills"),
        ("nti", "initiative:123"),
        ("bayt", "98765"),
        ("devpost", "45678"),
        ("un_volunteers", "1784888021274103"),
    ],
)
def test_supported_source_identity(source, identifier):
    identity = SourceIdentity(source, identifier)

    assert identity.source_name == source
    assert identity.source_opportunity_id == identifier
    assert identity.source_identity_key == f"id:{identifier}"


@pytest.mark.parametrize(
    "source, identifier",
    [
        ("wuzzuf", None),
        ("wuzzuf", ""),
        ("wuzzuf", "   "),
        ("wuzzuf", 123),
        ("wuzzuf", " ABC"),
        ("wuzzuf", "ABC "),
        ("wuzzuf", "ABC\x00"),
        ("linkedin", "123"),
        ("tanqeeb", "123"),
        ("amideast", "123"),
    ],
)
def test_invalid_source_identity(source, identifier):
    with pytest.raises(SourceIdentityError):
        SourceIdentity(source, identifier)


def test_identity_preserves_case():
    assert (
        SourceIdentity("wuzzuf", "ABC")
        != SourceIdentity("wuzzuf", "abc")
    )


def test_identity_preserves_leading_zeros():
    assert (
        SourceIdentity("bayt", "00123")
        != SourceIdentity("bayt", "123")
    )


def test_cross_source_identity():
    assert (
        SourceIdentity("bayt", "123")
        != SourceIdentity("forasna", "123")
    )


def test_identity_from_opportunity(opportunity):
    identity = SourceIdentity.from_opportunity(opportunity)

    assert identity.source_name == "wuzzuf"
    assert identity.source_identity_key == "id:ABC123"


def test_missing_identity_from_opportunity(opportunity):
    record = changed(
        opportunity,
        source_opportunity_id=None,
    )

    with pytest.raises(SourceIdentityError):
        SourceIdentity.from_opportunity(record)


def test_hash_version():
    assert HASH_VERSION == 1
    assert collection_runs.HASH_VERSION == HASH_VERSION


def test_hash_determinism(opportunity):
    restored = Opportunity.model_validate_json(
        opportunity.model_dump_json()
    )

    assert (
        generate_content_hash(opportunity)
        == generate_content_hash(restored)
    )

    assert (
        generate_observation_hash(opportunity)
        == generate_observation_hash(restored)
    )


@pytest.mark.parametrize(
    "updates, content_equal, observation_equal",
    [
        (
            {"salary_min": "12000"},
            False,
            False,
        ),
        (
            {"salary_min": "10000"},
            True,
            True,
        ),
        (
            {"required_skills": ["SQL", "Python"]},
            True,
            True,
        ),
        (
            {"required_skills": None},
            False,
            False,
        ),
        (
            {"required_skills": []},
            False,
            False,
        ),
        (
            {"raw_payload": {"id": "ABC123"}},
            True,
            False,
        ),
        (
            {
                "source_url":
                    "https://wuzzuf.net/jobs/p/ABC123-new"
            },
            True,
            False,
        ),
        (
            {"source_opportunity_id": "NEW123"},
            True,
            False,
        ),
    ],
)
def test_hash_semantics(
    opportunity,
    updates,
    content_equal,
    observation_equal,
):
    record = changed(opportunity, **updates)

    assert (
        generate_content_hash(record)
        == generate_content_hash(opportunity)
    ) == content_equal

    assert (
        generate_observation_hash(record)
        == generate_observation_hash(opportunity)
    ) == observation_equal


def test_collection_time_change(opportunity):
    record = changed(
        opportunity,
        collected_at=(
            opportunity.collected_at + timedelta(hours=1)
        ),
    )

    assert (
        generate_content_hash(record)
        == generate_content_hash(opportunity)
    )

    assert (
        generate_observation_hash(record)
        != generate_observation_hash(opportunity)
    )


def test_null_and_empty_arrays(opportunity):
    missing = changed(
        opportunity,
        required_skills=None,
    )

    empty = changed(
        opportunity,
        required_skills=[],
    )

    assert (
        generate_content_hash(missing)
        != generate_content_hash(empty)
    )

    assert (
        generate_observation_hash(missing)
        != generate_observation_hash(empty)
    )


def test_raw_array_order_preserved(opportunity):
    record = changed(
        opportunity,
        raw_payload={
            "id": "ABC123",
            "items": [3, 2, 1],
        },
    )

    assert (
        generate_content_hash(record)
        == generate_content_hash(opportunity)
    )

    assert (
        generate_observation_hash(record)
        != generate_observation_hash(opportunity)
    )


def test_raw_object_key_order_ignored(opportunity):
    record = changed(
        opportunity,
        raw_payload={
            "items": [1, 2, 3],
            "id": "ABC123",
        },
    )

    assert (
        generate_observation_hash(record)
        == generate_observation_hash(opportunity)
    )


@pytest.mark.parametrize(
    "field",
    ["published_at", "deadline"],
)
def test_relative_date_changes(opportunity, field):
    timestamp = opportunity.collected_at

    first = changed(
        opportunity,
        **{
            field: timestamp,
            f"{field}_raw": "2 hours ago",
            f"{field}_precision": "relative",
        },
    )

    second = changed(
        first,
        **{
            field: timestamp + timedelta(hours=1),
            f"{field}_raw": "1 hour ago",
        },
    )

    assert (
        generate_content_hash(first)
        == generate_content_hash(second)
    )

    assert (
        generate_observation_hash(first)
        != generate_observation_hash(second)
    )


@pytest.mark.parametrize(
    "field",
    ["published_at", "deadline"],
)
def test_exact_date_changes(opportunity, field):
    timestamp = opportunity.collected_at

    first = changed(
        opportunity,
        **{
            field: timestamp,
            f"{field}_precision": "exact",
        },
    )

    second = changed(
        first,
        **{
            field: timestamp + timedelta(days=1),
        },
    )

    assert (
        generate_content_hash(first)
        != generate_content_hash(second)
    )

    assert (
        generate_observation_hash(first)
        != generate_observation_hash(second)
    )


def test_hash_format(opportunity):
    content = generate_content_hash(opportunity)
    observation = generate_observation_hash(opportunity)

    assert len(content) == 64
    assert len(observation) == 64
    assert content != observation

    int(content, 16)
    int(observation, 16)
