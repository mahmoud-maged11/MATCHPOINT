
from copy import deepcopy
from unittest.mock import Mock

import pytest

from scrapers.models import Opportunity

from scrapers.sources.wuzzuf_api import (
    WuzzufAPIScraper,
)

from scrapers.storage.opportunities import (
    preserve_wuzzuf_organization,
)

from scrapers.utils.hashing import (
    generate_content_hash,
)

from test_wuzzuf_api import make_job


def make_opportunity():

    scraper = WuzzufAPIScraper(
        max_jobs=None,
        max_pages=None,
        page_size=20,
    )

    scraper.fetch_page = Mock(
        return_value=[make_job("1")]
    )

    scraper.fetch_company_name = Mock(
        return_value="Original Company"
    )

    result = scraper.run_with_result()

    assert result.accepted_count == 1

    return result.opportunities[0]


def incoming_from(original, **raw_changes):

    data = original.model_dump(mode="python")

    raw = deepcopy(data["raw_payload"])

    raw["_matchpoint_company_enrichment"] = (
        "temporary_failure"
    )

    raw.update(raw_changes)

    data["organization"] = None
    data["raw_payload"] = raw

    return Opportunity.model_validate(data)


def existing_from(original):

    return original.model_dump(mode="python")


def test_same_company_preserves_organization():

    original = make_opportunity()

    incoming = incoming_from(original)

    existing = existing_from(original)

    effective = preserve_wuzzuf_organization(
        incoming,
        existing,
    )

    assert effective.organization == "Original Company"

    assert incoming.organization is None

    assert effective.raw_payload == incoming.raw_payload

    assert generate_content_hash(effective) == (
        generate_content_hash(original)
    )


@pytest.mark.parametrize(
    "company_id",
    ["456", None, "", "abc", "0", 123, " 123"],
)
def test_unverified_identity_not_preserved(company_id):

    original = make_opportunity()

    incoming = incoming_from(
        original,
        company_id=company_id,
    )

    effective = preserve_wuzzuf_organization(
        incoming,
        existing_from(original),
    )

    assert effective is incoming
    assert effective.organization is None


def test_legacy_company_without_identity():

    original = make_opportunity()

    incoming = incoming_from(original)

    existing = existing_from(original)

    existing["raw_payload"].pop("company_id")

    assert preserve_wuzzuf_organization(
        incoming,
        existing,
    ) is incoming


@pytest.mark.parametrize(
    "visibility",
    [True, None, "false", 0],
)
def test_unverified_visibility_not_preserved(visibility):

    original = make_opportunity()

    incoming = incoming_from(
        original,
        attributes={"hideCompany": visibility},
    )

    assert preserve_wuzzuf_organization(
        incoming,
        existing_from(original),
    ) is incoming


def test_previously_hidden_company_not_preserved():

    original = make_opportunity()

    incoming = incoming_from(original)

    existing = existing_from(original)

    existing["raw_payload"]["attributes"][
        "hideCompany"
    ] = True

    assert preserve_wuzzuf_organization(
        incoming,
        existing,
    ) is incoming


@pytest.mark.parametrize(
    "reason",
    ["access_denied", "unknown", None],
)
def test_non_temporary_failure_not_preserved(reason):

    original = make_opportunity()

    incoming = incoming_from(
        original,
        _matchpoint_company_enrichment=reason,
    )

    assert preserve_wuzzuf_organization(
        incoming,
        existing_from(original),
    ) is incoming


@pytest.mark.parametrize(
    "organization",
    [None, "", "   "],
)
def test_invalid_previous_organization(organization):

    original = make_opportunity()

    incoming = incoming_from(original)

    existing = existing_from(original)

    existing["organization"] = organization

    assert preserve_wuzzuf_organization(
        incoming,
        existing,
    ) is incoming


def test_successful_enrichment_takes_precedence():

    original = make_opportunity()

    data = original.model_dump(mode="python")

    data["organization"] = "New Company Name"

    incoming = Opportunity.model_validate(data)

    assert preserve_wuzzuf_organization(
        incoming,
        existing_from(original),
    ) is incoming


def test_other_source_not_affected():

    original = make_opportunity()

    data = incoming_from(original).model_dump(
        mode="python"
    )

    data["source_name"] = "egyincs"

    incoming = Opportunity.model_validate(data)

    assert preserve_wuzzuf_organization(
        incoming,
        existing_from(original),
    ) is incoming
