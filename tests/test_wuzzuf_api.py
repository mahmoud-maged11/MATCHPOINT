from unittest.mock import Mock

import pytest
import requests
from scrapers.sources.wuzzuf_api import WuzzufAPIScraper


def make_job(job_id):

    return {
        "id": job_id,
        "attributes": {
            "slug": f"{job_id}-data-engineer",
            "uri": f"jobs/p/{job_id}-data-engineer",
            "title": "Data Engineer",
            "jobType": "job",
            "status": "active",
            "hideCompany": False,
            "hideSalary": True,
            "location": {
                "country": {
                    "name": "Egypt",
                    "code": "EG"
                }
            }
        },
        "relationships": {
            "company": {
                "data": {"id": "123"}
            }
        }
    }


def test_fetch_page():

    scraper = WuzzufAPIScraper()

    scraper.client.get = Mock()

    scraper.client.get.return_value.json.return_value = {
        "data": [make_job("1")]
    }

    records = scraper.fetch_page(0, 5)

    assert len(records) == 1

    scraper.client.get.assert_called_once_with(
        "https://wuzzuf.net/api/job",
        params={
            "page[limit]": 5,
            "page[offset]": 0,
            "sort": "-postedAt",
            "filter[status]": "active"
        }
    )


def test_company_cache():

    scraper = WuzzufAPIScraper()

    scraper.client.get = Mock()

    scraper.client.get.return_value.json.return_value = {
        "data": {
            "id": "123",
            "attributes": {
                "name": "Test Company"
            }
        }
    }

    assert scraper.fetch_company_name("123") == "Test Company"
    assert scraper.fetch_company_name("123") == "Test Company"

    assert scraper.client.get.call_count == 1


def test_pagination():

    scraper = WuzzufAPIScraper(
        max_jobs=4,
        page_size=2
    )

    scraper.fetch_page = Mock(
        side_effect=[
            [make_job("1"), make_job("2")],
            [make_job("3"), make_job("4")]
        ]
    )

    scraper.fetch_company_name = Mock(
        return_value="Test Company"
    )

    results = scraper.run()

    assert len(results) == 4

    assert scraper.fetch_page.call_args_list[0].args == (0, 2)
    assert scraper.fetch_page.call_args_list[1].args == (2, 2)


def test_duplicate_jobs():

    scraper = WuzzufAPIScraper(
        max_jobs=4,
        page_size=2
    )

    scraper.fetch_page = Mock(
        side_effect=[
            [make_job("1"), make_job("2")],
            [make_job("1"), make_job("2")]
        ]
    )

    scraper.fetch_company_name = Mock(
        return_value="Test Company"
    )

    results = scraper.run()

    assert len(results) == 2


def test_empty_page():

    scraper = WuzzufAPIScraper()

    scraper.fetch_page = Mock(return_value=[])

    assert scraper.run() == []


def test_inactive_job():

    scraper = WuzzufAPIScraper()

    job = make_job("1")
    job["attributes"]["status"] = "expired"

    scraper.fetch_page = Mock(return_value=[job])

    assert scraper.run() == []


def test_non_egyptian_job():

    scraper = WuzzufAPIScraper()

    job = make_job("1")

    job["attributes"]["location"]["country"]["code"] = "US"

    scraper.fetch_page = Mock(return_value=[job])

    assert scraper.run() == []


def test_invalid_record():

    scraper = WuzzufAPIScraper()

    job = make_job("1")

    del job["attributes"]["title"]

    scraper.fetch_page = Mock(return_value=[job])

    scraper.fetch_company_name = Mock(
        return_value="Test Company"
    )

    assert scraper.run() == []
    assert len(scraper.invalid_records) == 1


def test_hidden_company():

    scraper = WuzzufAPIScraper()

    job = make_job("1")
    job["attributes"]["hideCompany"] = True

    scraper.fetch_company_name = Mock()

    assert scraper.extract_company_name(job) is None

    scraper.fetch_company_name.assert_not_called()


def test_invalid_max_jobs():

    with pytest.raises(ValueError):
        WuzzufAPIScraper(max_jobs=0)



def test_company_not_found():

    scraper = WuzzufAPIScraper()

    response = Mock()
    response.status_code = 404

    scraper.client.get = Mock(
        side_effect=requests.HTTPError(
            response=response
        )
    )

    assert scraper.fetch_company_name("123") is None
    assert scraper.fetch_company_name("123") is None

    assert scraper.client.get.call_count == 1


def test_company_forbidden():

    scraper = WuzzufAPIScraper()

    response = Mock()
    response.status_code = 403

    scraper.client.get = Mock(
        side_effect=requests.HTTPError(
            response=response
        )
    )

    with pytest.raises(requests.HTTPError):
        scraper.fetch_company_name("123")


def test_expired_active_job():

    scraper = WuzzufAPIScraper()

    job = make_job("1")

    job["attributes"]["expireAt"] = (
        "01/01/2000 10:00:00"
    )

    scraper.fetch_page = Mock(return_value=[job])

    scraper.fetch_company_name = Mock()

    assert scraper.run() == []

    assert scraper.stats["expired"] == 1

    scraper.fetch_company_name.assert_not_called()


def test_malformed_record_does_not_stop_collection():

    scraper = WuzzufAPIScraper()

    scraper.fetch_page = Mock(
        return_value=[
            None,
            make_job("1")
        ]
    )

    scraper.fetch_company_name = Mock(
        return_value="Test Company"
    )

    results = scraper.run()

    assert len(results) == 1
    assert scraper.stats["invalid"] == 1
    assert scraper.stats["accepted"] == 1


def test_invalid_job_skips_company_request():

    scraper = WuzzufAPIScraper()

    job = make_job("1")

    del job["attributes"]["title"]

    scraper.fetch_page = Mock(return_value=[job])

    scraper.fetch_company_name = Mock()

    assert scraper.run() == []

    scraper.fetch_company_name.assert_not_called()