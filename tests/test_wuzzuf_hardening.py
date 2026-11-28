from unittest.mock import Mock

import pytest
import requests

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from scrapers.sources.wuzzuf_api import (
    WuzzufAPIScraper,
    CompanyIdentityMismatchError,
)

from test_wuzzuf_api import make_job
from test_wuzzuf_completeness import make_scraper


def valid_company():

    return {
        "data": {
            "id": "123",
            "attributes": {
                "name": "Test Company",
            },
        },
    }


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"data": None},
        {"data": []},
        {"data": {"id": "123"}},
        {
            "data": {
                "id": "123",
                "attributes": [],
            },
        },
        {
            "data": {
                "attributes": {
                    "name": "Test Company",
                },
            },
        },
    ],
)
def test_invalid_company_response_not_cached(payload):

    scraper = WuzzufAPIScraper()

    scraper.client.get = Mock()

    response = scraper.client.get.return_value

    response.json.side_effect = [
        payload,
        valid_company(),
    ]

    with pytest.raises(ValueError):

        scraper.fetch_company_name("123")

    assert scraper.fetch_company_name(
        "123"
    ) == "Test Company"

    assert scraper.fetch_company_name(
        "123"
    ) == "Test Company"

    assert scraper.client.get.call_count == 2


def test_company_identity_mismatch_not_cached():

    scraper = WuzzufAPIScraper()

    scraper.client.get = Mock()

    incorrect = valid_company()

    incorrect["data"]["id"] = "999"

    scraper.client.get.return_value.json.side_effect = [
        incorrect,
        valid_company(),
    ]

    with pytest.raises(CompanyIdentityMismatchError):

        scraper.fetch_company_name("123")

    assert scraper.fetch_company_name(
        "123"
    ) == "Test Company"

    assert scraper.fetch_company_name(
        "123"
    ) == "Test Company"

    assert scraper.client.get.call_count == 2


def test_company_invalid_json_not_cached():

    scraper = WuzzufAPIScraper()

    scraper.client.get = Mock()

    scraper.client.get.return_value.json.side_effect = [
        requests.exceptions.JSONDecodeError(
            "Invalid JSON",
            "invalid",
            0,
        ),
        valid_company(),
    ]

    with pytest.raises(ValueError) as error:

        scraper.fetch_company_name("123")

    assert not isinstance(
        error.value,
        requests.RequestException,
    )

    assert scraper.fetch_company_name(
        "123"
    ) == "Test Company"

    assert scraper.client.get.call_count == 2


def test_listing_invalid_json_classification():

    scraper = WuzzufAPIScraper()

    scraper.client.get = Mock()

    scraper.client.close = Mock()

    scraper.client.get.return_value.json.side_effect = (
        requests.exceptions.JSONDecodeError(
            "Invalid JSON",
            "invalid",
            0,
        )
    )

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED

    assert result.stop_reason == StopReason.PARSING_ERROR

    assert result.returned_count == 0


def test_company_mismatch_preserves_previous_results():

    scraper = make_scraper([
        [make_job("1"), make_job("2")],
    ])

    scraper.fetch_company_name.side_effect = [
        "Test Company",
        CompanyIdentityMismatchError(
            "Company API ID mismatch"
        ),
    ]

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL

    assert result.stop_reason == StopReason.PARSING_ERROR

    assert result.accepted_count == 1

    assert result.rejected_count == 0

    assert result.opportunities[0].source_opportunity_id == "1"

    assert not result.source_exhausted


@pytest.mark.parametrize(
    "error",
    [
        TypeError("Unexpected programming error"),
        AttributeError("Unexpected programming error"),
        RuntimeError("Unexpected programming error"),
    ],
)
def test_unexpected_company_errors_propagate(error):

    scraper = make_scraper([
        [make_job("1")],
    ])

    scraper.fetch_company_name.side_effect = error

    with pytest.raises(type(error)):

        scraper.run_with_result()

    scraper.client.close.assert_called_once()
