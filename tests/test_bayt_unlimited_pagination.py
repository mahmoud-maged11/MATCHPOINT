
import pytest

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)

from test_bayt import (
    scraper,
    setup_responses,
    make_response,
    make_listing,
    make_detail,
    job_url,
    LISTING,
)


@pytest.mark.parametrize(
    "overlap",
    [False, True],
)
def test_unlimited_pagination(scraper, overlap):

    scraper.max_jobs = None
    scraper.max_pages = None

    second = LISTING + "?page=2"

    second_ids = (
        [102, 103]
        if overlap
        else [103]
    )

    setup_responses(scraper, {
        LISTING: make_response(
            LISTING,
            make_listing([101, 102], 2),
        ),
        second: make_response(
            second,
            make_listing(second_ids),
        ),
        **{
            job_url(i): make_response(
                job_url(i),
                make_detail(),
            )
            for i in (101, 102, 103)
        },
    })

    result = scraper.run_with_result()

    assert result.accepted_count == 3
    assert result.rejected_count == 0

    assert scraper.stats["listing_pages"] == 2
    assert scraper.stats["details_fetched"] == 3

    assert scraper.stats["pagination_overlaps"] == int(overlap)
    assert scraper.stats["overlapping_job_ids"] == int(overlap)

    if overlap:

        assert result.status == CollectionStatus.PARTIAL
        assert result.stop_reason == StopReason.SOURCE_ERROR
        assert not result.source_exhausted

    else:

        assert result.status == CollectionStatus.COMPLETED
        assert result.source_exhausted


def test_unlimited_http_failure_preserves_data(scraper):

    scraper.max_jobs = None
    scraper.max_pages = None

    second = LISTING + "?page=2"

    setup_responses(scraper, {
        LISTING: make_response(
            LISTING,
            make_listing([101], 2),
        ),
        job_url(101): make_response(
            job_url(101),
            make_detail(),
        ),
        second: make_response(
            second, "", 503
        ),
    })

    result = scraper.run_with_result()

    assert result.accepted_count == 1
    assert result.status == CollectionStatus.PARTIAL
    assert result.stop_reason == StopReason.SOURCE_ERROR
    assert not result.source_exhausted
