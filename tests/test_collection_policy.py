from uuid import uuid4

import pytest

from scrapers.collection_policy import (
    CollectionPolicy,
    CoverageStatus,
    LoadStrategy,
    checkpoint_coverage_eligible,
    classify_coverage,
)

from scrapers.collection_result import (
    CollectionResult,
    CollectionStatus,
    StopReason,
)


def make_result(status, reason):

    return CollectionResult(
        run_id=uuid4(),
        source_name="egyincs",
        status=status,
        stop_reason=reason,
    )


def test_default_policy_preserves_existing_limits():

    policy = CollectionPolicy()

    assert policy.strategy == LoadStrategy.BOUNDED
    assert policy.max_jobs == 20
    assert policy.max_pages == 10
    assert policy.page_size == 20


@pytest.mark.parametrize(
    "strategy",
    [LoadStrategy.FULL, LoadStrategy.INCREMENTAL],
)
def test_optional_limits(strategy):

    policy = CollectionPolicy(
        strategy=strategy,
        max_jobs=None,
        max_pages=None,
        page_size=20,
    )

    assert policy.remaining_jobs(100000) is None
    assert not policy.jobs_limit_reached(100000)
    assert not policy.pages_limit_reached(100000)
    assert policy.next_page_size(100000) == 20


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_jobs", 0),
        ("max_jobs", -1),
        ("max_jobs", True),
        ("max_jobs", 1.5),
        ("max_pages", 0),
        ("max_pages", False),
        ("page_size", 0),
        ("page_size", None),
        ("page_size", "20"),
    ],
)
def test_invalid_limits(field, value):

    with pytest.raises(ValueError):
        CollectionPolicy(**{field: value})


@pytest.mark.parametrize(
    "field",
    ["max_jobs", "max_pages"],
)
def test_bounded_requires_limits(field):

    with pytest.raises(ValueError):
        CollectionPolicy(**{field: None})


def test_invalid_strategy():

    with pytest.raises(TypeError):
        CollectionPolicy(strategy="full")


@pytest.mark.parametrize(
    "accepted,remaining,reached,size",
    [
        (0, 20, False, 20),
        (15, 5, False, 5),
        (19, 1, False, 1),
        (20, 0, True, 0),
        (21, 0, True, 0),
    ],
)
def test_job_boundaries(
    accepted, remaining, reached, size
):

    policy = CollectionPolicy()

    assert policy.remaining_jobs(accepted) == remaining
    assert policy.jobs_limit_reached(accepted) == reached
    assert policy.next_page_size(accepted) == size


@pytest.mark.parametrize(
    "fetched,reached",
    [(0, False), (9, False), (10, True), (11, True)],
)
def test_page_boundaries(fetched, reached):

    assert (
        CollectionPolicy().pages_limit_reached(fetched)
        == reached
    )


@pytest.mark.parametrize("value", [-1, True, 1.5, None])
def test_invalid_progress(value):

    policy = CollectionPolicy()

    with pytest.raises(ValueError):
        policy.remaining_jobs(value)

    with pytest.raises(ValueError):
        policy.pages_limit_reached(value)


@pytest.mark.parametrize(
    "status,reason,expected",
    [
        (
            CollectionStatus.COMPLETED,
            StopReason.SOURCE_EXHAUSTED,
            CoverageStatus.EXHAUSTED,
        ),
        (
            CollectionStatus.COMPLETED,
            StopReason.REQUESTED_LIMIT,
            CoverageStatus.LIMITED,
        ),
        (
            CollectionStatus.COMPLETED,
            StopReason.INPUT_EXHAUSTED,
            CoverageStatus.INPUT_ONLY,
        ),
        (
            CollectionStatus.PARTIAL,
            StopReason.SOURCE_ERROR,
            CoverageStatus.INCOMPLETE,
        ),
        (
            CollectionStatus.PARTIAL,
            StopReason.PARSING_ERROR,
            CoverageStatus.INCOMPLETE,
        ),
        (
            CollectionStatus.FAILED,
            StopReason.SOURCE_ERROR,
            CoverageStatus.INCOMPLETE,
        ),
        (
            CollectionStatus.ABORTED,
            StopReason.INTERRUPTED,
            CoverageStatus.INCOMPLETE,
        ),
    ],
)
def test_coverage(status, reason, expected):

    result = make_result(status, reason)

    assert classify_coverage(result) == expected


@pytest.mark.parametrize(
    "strategy",
    list(LoadStrategy),
)
@pytest.mark.parametrize(
    "reason",
    [
        StopReason.SOURCE_EXHAUSTED,
        StopReason.REQUESTED_LIMIT,
        StopReason.INPUT_EXHAUSTED,
    ],
)
@pytest.mark.parametrize("verified", [True, False])
def test_checkpoint_coverage_gate(
    strategy, reason, verified
):

    result = make_result(
        CollectionStatus.COMPLETED,
        reason,
    )

    expected = (
        strategy != LoadStrategy.BOUNDED
        and reason == StopReason.SOURCE_EXHAUSTED
        and verified
    )

    assert checkpoint_coverage_eligible(
        result,
        strategy=strategy,
        source_boundary_verified=verified,
    ) == expected


def test_incomplete_collection_cannot_advance():

    result = make_result(
        CollectionStatus.PARTIAL,
        StopReason.SOURCE_ERROR,
    )

    assert not checkpoint_coverage_eligible(
        result,
        strategy=LoadStrategy.INCREMENTAL,
        source_boundary_verified=True,
    )


def test_invalid_boundary_evidence():

    result = make_result(
        CollectionStatus.COMPLETED,
        StopReason.SOURCE_EXHAUSTED,
    )

    with pytest.raises(TypeError):
        checkpoint_coverage_eligible(
            result,
            strategy=LoadStrategy.FULL,
            source_boundary_verified="true",
        )
