import inspect

import pytest

from scrapers.main import (
    build_parser,
    validate_arguments,
    create_scraper,
)

from scrapers.sources.forasna import ForasnaScraper
from scrapers.sources.forasna_mapper import ForasnaMapper


@pytest.mark.parametrize(
    "max_jobs,max_pages",
    [
        (None, None),
        (None, 2),
        (10, None),
        (10, 2),
    ],
)
def test_optional_collection_limits(max_jobs, max_pages):

    scraper = ForasnaScraper(
        max_jobs=max_jobs,
        max_pages=max_pages,
    )

    try:
        assert scraper.max_jobs == max_jobs
        assert scraper.max_pages == max_pages
    finally:
        scraper.client.close()


@pytest.mark.parametrize(
    "value",
    [True, False, 0, -1, 1.5, "10"],
)
@pytest.mark.parametrize(
    "field",
    ["max_jobs", "max_pages"],
)
def test_invalid_collection_limits(field, value):

    with pytest.raises(ValueError):
        ForasnaScraper(**{field: value})


def test_full_cli_has_no_implicit_limits():

    parser = build_parser()

    args = parser.parse_args([
        "--source", "forasna",
        "--mode", "live",
        "--load-strategy", "full",
    ])

    mode = validate_arguments(parser, args)

    assert mode == "live"
    assert args.max_jobs is None
    assert args.max_pages is None

    scraper = create_scraper(args, mode)

    try:
        assert scraper.max_jobs is None
        assert scraper.max_pages is None
    finally:
        scraper.client.close()


def test_bounded_cli_preserves_defaults():

    parser = build_parser()

    args = parser.parse_args([
        "--source", "forasna",
        "--mode", "live",
    ])

    validate_arguments(parser, args)

    assert args.max_jobs == 20
    assert args.max_pages == 10


def test_mapper_supports_parsed_input():

    parameters = inspect.signature(
        ForasnaMapper.map_job
    ).parameters

    assert parameters["soup"].default is None
    assert parameters["posting"].default is None
