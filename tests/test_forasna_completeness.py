from uuid import uuid4

import pytest
import requests

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from test_forasna import (
    BASE,
    SEARCH,
    NEXT,
    job_url,
    search_html,
    detail_html,
    make_scraper,
)


def test_source_exhausted():

    scraper = make_scraper({
        SEARCH: search_html([1]),
        job_url(1): detail_html(1),
    })

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.accepted_count == 1
    assert result.stop_reason == StopReason.SOURCE_EXHAUSTED


def test_empty_source():

    scraper = make_scraper({
        SEARCH: search_html([]),
    })

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.source_exhausted
    assert result.returned_count == 0


def test_requested_job_limit():

    scraper = make_scraper(
        {
            SEARCH: search_html([1, 2]),
            job_url(1): detail_html(1),
        },
        max_jobs=1,
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert result.accepted_count == 1
    assert not result.source_exhausted


def test_requested_page_limit():

    scraper = make_scraper(
        {
            SEARCH: search_html([1], NEXT),
            job_url(1): detail_html(1),
        },
        max_pages=1,
    )

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.stop_reason == StopReason.REQUESTED_LIMIT
    assert result.accepted_count == 1
    assert not result.source_exhausted


def test_repeated_pagination_url():

    scraper = make_scraper({
        SEARCH: search_html([1], SEARCH),
        job_url(1): detail_html(1),
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert not result.source_exhausted


def test_duplicate_only_page():

    scraper = make_scraper({
        SEARCH: search_html([1], NEXT),
        NEXT: search_html([1]),
        job_url(1): detail_html(1),
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert scraper.stats["duplicates"] == 1


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("Connection lost"),
        requests.Timeout("Request timed out"),
        PermissionError("Access denied"),
    ],
)
def test_search_failure_preserves_results(error):

    scraper = make_scraper({
        SEARCH: search_html([1], NEXT),
        NEXT: error,
        job_url(1): detail_html(1),
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("Connection lost"),
        requests.Timeout("Request timed out"),
        PermissionError("Access denied"),
    ],
)
def test_detail_failure_preserves_results(error):

    scraper = make_scraper({
        SEARCH: search_html([1, 2]),
        job_url(1): detail_html(1),
        job_url(2): error,
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert result.accepted_count == 1
    assert result.rejected_count == 0

    assert result.opportunities[0].source_opportunity_id == "1"


def test_invalid_search_page_preserves_results():

    scraper = make_scraper({
        SEARCH: search_html([1], NEXT),
        NEXT: "<html>Unexpected response</html>",
        job_url(1): detail_html(1),
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1
    assert not result.source_exhausted


def test_invalid_pagination_preserves_results():

    scraper = make_scraper({
        SEARCH: search_html(
            [1],
            "https://example.com/jobs",
        ),
        job_url(1): detail_html(1),
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert result.accepted_count == 1


def test_invalid_job_links_not_source_exhaustion():

    scraper = make_scraper({
        SEARCH: """
        <html>
            <div id="search-results-container">
                <div class="result-wrp">
                    <h2 class="job-title">
                        <a href="https://example.com">
                            Invalid job
                        </a>
                    </h2>
                </div>
            </div>
        </html>
        """,
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert not result.source_exhausted


def test_empty_page_with_next_link():

    scraper = make_scraper({
        SEARCH: search_html([], NEXT),
    })

    result = scraper.run_with_result()

    assert result.status == CollectionStatus.FAILED
    assert result.stop_reason == StopReason.PARSING_ERROR
    assert not result.source_exhausted


@pytest.mark.parametrize("status_code", [404, 410])
def test_unavailable_job_does_not_fail_collection(status_code):

    response = requests.Response()
    response.status_code = status_code

    scraper = make_scraper({
        SEARCH: search_html([1, 2]),
        job_url(1): requests.HTTPError(response=response),
        job_url(2): detail_html(2),
    })

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.accepted_count == 1
    assert result.rejected_count == 0
    assert scraper.stats["unavailable"] == 1


def test_invalid_record_with_shared_run_id():

    scraper = make_scraper({
        SEARCH: search_html([1, 2]),
        job_url(1): "<html></html>",
        job_url(2): detail_html(2),
    })

    run_id = uuid4()

    result = scraper.run_with_result(
        run_id=run_id,
    )

    assert result.scope_completed
    assert result.run_id == run_id
    assert result.accepted_count == 1
    assert result.rejected_count == 1
    assert result.returned_count == 2

    assert result.invalid_records[0].run_id == str(run_id)


def test_filtered_jobs_not_invalid_records():

    scraper = make_scraper({
        SEARCH: search_html([1, 2, 3]),
        job_url(1): detail_html(1, country="SA"),
        job_url(2): detail_html(2, active=False),
        job_url(3): detail_html(
            3,
            deadline="2020-01-01T00:00:00+02:00",
        ),
    })

    result = scraper.run_with_result()

    assert result.scope_completed
    assert result.returned_count == 0
    assert scraper.stats["non_egyptian"] == 1
    assert scraper.stats["inactive"] == 1
    assert scraper.stats["expired"] == 1


def test_initial_request_failure_propagates():

    scraper = make_scraper({
        SEARCH: requests.ConnectionError("Connection lost"),
    })

    with pytest.raises(requests.ConnectionError):

        scraper.run_with_result()

    assert scraper.last_result.status == CollectionStatus.FAILED
    assert scraper.last_result.stop_reason == StopReason.SOURCE_ERROR

    scraper.client.close.assert_called_once()


def test_unexpected_programming_error_propagates():

    scraper = make_scraper({
        SEARCH: RuntimeError("Unexpected programming error"),
    })

    with pytest.raises(
        RuntimeError,
        match="Unexpected programming error",
    ):

        scraper.run_with_result()

    assert scraper.last_result.status == CollectionStatus.FAILED

    scraper.client.close.assert_called_once()
