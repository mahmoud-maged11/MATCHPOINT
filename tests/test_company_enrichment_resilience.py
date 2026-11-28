from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

from scrapers.sources.egyincs import EgyincsScraper
from scrapers.sources.egyincs_mapper import EgyincsMapper
from scrapers.storage.opportunities import (
    preserve_egyincs_organization,
)
from scrapers.utils.hashing import generate_content_hash


def opportunity(company_id=123, organization=None, denied=True):

    result = EgyincsMapper.map_record(
        {
            "id": 12345,
            "status": "publish",
            "title": {"rendered": "Software Engineer Job"},
            "content": {"rendered": "Software engineering"},
            "link": "https://egyincs.com/opportunities/example/",
            "date_gmt": "2026-01-01T12:00:00",
            "felan-jobs_select_company": company_id,
        },
        endpoint="jobs",
        company_name=organization,
        observed_at=datetime.now(timezone.utc),
    )

    if denied:

        result = result.model_copy(
            update={
                "raw_payload": {
                    **result.raw_payload,
                    "_matchpoint_company_enrichment":
                        "access_denied",
                }
            }
        )

    return result


def existing(company_id=123, organization="Known Company"):

    return {
        "organization": organization,
        "raw_payload": {
            "company_id": company_id,
        },
    }


@pytest.mark.parametrize("status", [401, 403])
def test_access_failure_is_optional(status):

    scraper = EgyincsScraper(endpoint="jobs")

    response = requests.Response()
    response.status_code = status

    scraper.fetch = Mock(
        side_effect=requests.HTTPError(
            response=response
        )
    )

    try:

        assert scraper.fetch_company_name(123) is None
        assert scraper.fetch_company_name(123) is None

        assert scraper.fetch.call_count == 1
        assert "123" in scraper.company_access_failures
        assert "123" not in scraper.company_cache
        assert scraper.stats["company_access_failures"] == 1

    finally:

        scraper.client.close()


def test_preserves_known_organization():

    incoming = opportunity()

    effective = preserve_egyincs_organization(
        incoming,
        existing(),
    )

    assert incoming.organization is None
    assert effective.organization == "Known Company"

    expected = opportunity(
        organization="Known Company",
        denied=False,
    )

    assert (
        generate_content_hash(effective)
        == generate_content_hash(expected)
    )


@pytest.mark.parametrize(
    "incoming_id,previous_id",
    [
        (123, 456),
        (None, None),
        (0, 0),
        ("invalid", "invalid"),
    ],
)
def test_does_not_copy_unrelated_company(
    incoming_id,
    previous_id,
):

    incoming = opportunity(company_id=incoming_id)

    assert preserve_egyincs_organization(
        incoming,
        existing(company_id=previous_id),
    ) is incoming


def test_authoritative_name_is_not_overwritten():

    incoming = opportunity(
        organization="New Company"
    )

    assert preserve_egyincs_organization(
        incoming,
        existing(),
    ) is incoming


def test_normal_missing_name_unchanged():

    incoming = opportunity(denied=False)

    assert preserve_egyincs_organization(
        incoming,
        existing(),
    ) is incoming


def test_no_previous_name():

    incoming = opportunity()

    assert preserve_egyincs_organization(
        incoming,
        existing(organization=None),
    ) is incoming


def test_deferred_enrichment_blocks_checkpoint():

    scraper = EgyincsScraper(endpoint="jobs")

    scraper.incremental_window = Mock()

    scraper.pagination_evidence = Mock(
        boundary_verified=True,
        expected_total=1,
    )

    scraper.stats = {
        "company_enrichment_deferred": 1,
        "duplicates": 0,
        "unpublished": 0,
    }

    result = Mock(
        scope_completed=True,
        source_exhausted=True,
        rejected_count=0,
        accepted_count=1,
    )

    try:

        assert not scraper.incremental_coverage_verified(
            result
        )

        scraper.stats["company_enrichment_deferred"] = 0

        assert scraper.incremental_coverage_verified(
            result
        )

    finally:

        scraper.client.close()
