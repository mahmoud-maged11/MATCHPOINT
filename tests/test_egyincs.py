from unittest.mock import Mock

import pytest
import requests

from scrapers.sources.egyincs import EgyincsScraper


def make_record(source_id, endpoint="jobs"):

    path = (
        "courses"
        if endpoint == "lp_course"
        else "opportunities"
    )

    return {
        "id": source_id,
        "status": "publish",
        "title": {
            "rendered": f"Opportunity {source_id}"
        },
        "content": {
            "rendered": "<p>Test description</p>"
        },
        "link": (
            f"https://egyincs.com/{path}/test-{source_id}/"
        ),
        "date_gmt": "2026-11-25T08:00:00",
        "felan-jobs_select_company": "100",
        "_embedded": {
            "wp:term": [
                [
                    {
                        "taxonomy": "jobs-type",
                        "slug": "job",
                        "name": "Job",
                    }
                ]
            ]
        },
    }


def make_scraper(**kwargs):

    scraper = EgyincsScraper(**kwargs)

    scraper.client.close()
    scraper.client = Mock()

    scraper.load_robots = Mock()

    scraper.fetch_company_name = Mock(
        return_value="Test Company"
    )

    return scraper


def test_collect_jobs():

    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=2,
    )

    scraper.fetch_page = Mock(
        return_value=(
            [make_record(1), make_record(2)],
            1,
        )
    )

    results = scraper.run()

    assert len(results) == 2
    assert scraper.stats["accepted"] == 2
    assert scraper.stats["jobs"] == 2
    assert results[0].organization == "Test Company"


def test_pagination():

    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=4,
        page_size=2,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            ([make_record(1), make_record(2)], 2),
            ([make_record(3), make_record(4)], 2),
        ]
    )

    results = scraper.run()

    assert len(results) == 4
    assert scraper.stats["pages"] == 2


def test_duplicate_records():

    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=3,
        page_size=2,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            ([make_record(1), make_record(2)], 2),
            ([make_record(2), make_record(3)], 2),
        ]
    )

    results = scraper.run()

    assert len(results) == 3
    assert scraper.stats["duplicates"] == 1


def test_max_jobs():

    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=1,
    )

    scraper.fetch_page = Mock(
        return_value=(
            [make_record(1), make_record(2)],
            1,
        )
    )

    assert len(scraper.run()) == 1


def test_max_pages():

    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=10,
        page_size=2,
        max_pages=1,
    )

    scraper.fetch_page = Mock(
        return_value=(
            [make_record(1), make_record(2)],
            100,
        )
    )

    assert len(scraper.run()) == 2
    assert scraper.stats["pages"] == 1


def test_empty_page():

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch_page = Mock(
        return_value=([], 0)
    )

    assert scraper.run() == []


def test_invalid_record():

    scraper = make_scraper(endpoint="jobs")

    invalid = make_record(1)
    invalid["title"]["rendered"] = ""

    scraper.fetch_page = Mock(
        return_value=(
            [invalid, make_record(2)],
            1,
        )
    )

    assert len(scraper.run()) == 1
    assert scraper.stats["invalid"] == 1
    assert len(scraper.invalid_records) == 1


def test_unpublished_record():

    scraper = make_scraper(endpoint="jobs")

    record = make_record(1)
    record["status"] = "draft"

    scraper.fetch_page = Mock(
        return_value=([record], 1)
    )

    assert scraper.run() == []
    assert scraper.stats["unpublished"] == 1


def test_collect_courses():

    scraper = make_scraper(
        endpoint="lp_course",
        max_jobs=2,
    )

    scraper.fetch_page = Mock(
        return_value=(
            [
                make_record(1, "lp_course"),
                make_record(2, "lp_course"),
            ],
            1,
        )
    )

    results = scraper.run()

    assert len(results) == 2

    assert all(
        item.opportunity_type == "training"
        for item in results
    )

    scraper.fetch_company_name.assert_not_called()


def test_collect_all_endpoints():

    scraper = make_scraper(
        endpoint="all",
        max_jobs=4,
    )

    scraper.fetch_page = Mock(
        side_effect=[
            (
                [
                    make_record(1),
                    make_record(2),
                    make_record(3),
                ],
                1,
            ),
            (
                [make_record(4, "lp_course")],
                1,
            ),
        ]
    )

    results = scraper.run()

    assert len(results) == 4
    assert scraper.stats["jobs"] == 3
    assert scraper.stats["lp_course"] == 1


def test_unknown_status_retained():

    scraper = make_scraper(
        endpoint="jobs",
        max_jobs=1,
    )

    scraper.fetch_page = Mock(
        return_value=([make_record(1)], 1)
    )

    results = scraper.run()

    assert results[0].status == "unknown"
    assert scraper.stats["unknown_status"] == 1


def test_company_cache():

    scraper = EgyincsScraper()

    scraper.client.close()
    scraper.client = Mock()

    response = Mock()

    response.json.return_value = {
        "id": 100,
        "title": {
            "rendered": "Test Company"
        },
    }

    scraper.fetch = Mock(return_value=response)

    assert scraper.fetch_company_name("100") == "Test Company"
    assert scraper.fetch_company_name("100") == "Test Company"

    scraper.fetch.assert_called_once()


def test_company_not_found():

    scraper = EgyincsScraper()

    scraper.client.close()
    scraper.client = Mock()

    response = requests.Response()
    response.status_code = 404

    scraper.fetch = Mock(
        side_effect=requests.HTTPError(
            response=response
        )
    )

    assert scraper.fetch_company_name("100") is None
    assert scraper.fetch_company_name("100") is None

    scraper.fetch.assert_called_once()


def test_robots_disallowed():

    scraper = EgyincsScraper()

    scraper.client.close()
    scraper.client = Mock()

    scraper.robots = Mock()

    scraper.robots.can_fetch.return_value = False

    with pytest.raises(PermissionError):
        scraper.fetch("jobs")

    scraper.client.get.assert_not_called()


def test_api_error_propagates():

    scraper = make_scraper(endpoint="jobs")

    scraper.fetch_page = Mock(
        side_effect=requests.HTTPError("API error")
    )

    with pytest.raises(requests.HTTPError):
        scraper.run()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_jobs": 0},
        {"max_pages": 0},
        {"page_size": 0},
        {"page_size": 21},
        {"endpoint": "invalid"},
    ],
)
def test_invalid_configuration(kwargs):

    with pytest.raises(ValueError):
        EgyincsScraper(**kwargs)

def test_job_fields_configuration():

    fields = EgyincsScraper.JOB_FIELDS.split(",")

    required_fields = {
        "felan-jobs_salary_show",
        "felan-jobs_salary_rate",
        "felan-jobs_currency_type",
        "felan-jobs_salary_minimum",
        "felan-jobs_salary_maximum",
        "_links",
        "_embedded",
    }

    assert required_fields.issubset(set(fields))
    assert "" not in fields
    assert len(fields) == len(set(fields))