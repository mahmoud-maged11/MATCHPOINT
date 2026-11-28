import pytest

from scrapers.models import Opportunity
from scrapers.storage.identity import (
    MAX_SOURCE_ID_BYTES,
    SourceIdentity,
    SourceIdentityError,
)


@pytest.mark.parametrize(
    "identifier",
    [
        "A" * 511,
        "A" * 512,
        "\u0627" * 256,
        "\U0001F600" * 128,
    ],
)
def test_identity_accepts_valid_byte_length(identifier):
    identity = SourceIdentity("wuzzuf", identifier)

    assert len(identifier.encode("utf-8")) <= MAX_SOURCE_ID_BYTES
    assert identity.source_opportunity_id == identifier
    assert identity.source_identity_key == f"id:{identifier}"


@pytest.mark.parametrize(
    "identifier",
    [
        "A" * 513,
        "A" * 10000,
        "\u0627" * 257,
        "\U0001F600" * 129,
    ],
)
def test_identity_rejects_oversized_identifiers(identifier):
    with pytest.raises(
        SourceIdentityError,
        match="exceeds",
    ):
        SourceIdentity("wuzzuf", identifier)


@pytest.mark.parametrize(
    "identifier",
    [
        "\ud800",
        "\udfff",
        "ABC\ud800",
    ],
)
def test_identity_rejects_invalid_unicode(identifier):
    with pytest.raises(
        SourceIdentityError,
        match="invalid Unicode",
    ):
        SourceIdentity("wuzzuf", identifier)


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
def test_identity_limit_applies_to_all_sources(source):
    with pytest.raises(SourceIdentityError):
        SourceIdentity(source, "X" * 513)


def test_identity_does_not_truncate_identifier():
    identifier = "A" * 512

    identity = SourceIdentity("wuzzuf", identifier)

    assert identity.source_opportunity_id == identifier
    assert identity.source_identity_key == "id:" + identifier


def test_identity_from_opportunity_rejects_oversized_id():
    opportunity = Opportunity(
        source_name="wuzzuf",
        source_opportunity_id="A" * 513,
        source_url="https://wuzzuf.net/jobs/p/ABC123",
        title="Data Engineer",
        opportunity_type="job",
        raw_payload={"id": "A" * 513},
    )

    with pytest.raises(SourceIdentityError):
        SourceIdentity.from_opportunity(opportunity)
