
import pytest

from scrapers.sources.nti import NTIScraper
from scrapers.sources.nti_mapper import NTIMapper


@pytest.mark.parametrize(
    "attribute",
    ["max_jobs", "max_pages"],
)
@pytest.mark.parametrize(
    "value",
    [0, -1, True, False, 1.5, "10"],
)
def test_invalid_collection_limits(attribute, value):

    with pytest.raises(ValueError):
        NTIScraper(**{attribute: value})


def test_unlimited_collection_limits():

    scraper = NTIScraper(
        max_jobs=None,
        max_pages=None,
    )

    try:
        assert scraper.max_jobs is None
        assert scraper.max_pages is None

    finally:
        scraper.client.close()


def test_production_cli_full_mode(tmp_path):

    from scrapers.main import (
        build_parser,
        validate_arguments,
        create_scraper,
    )

    parser = build_parser()

    args = parser.parse_args([
        "--source", "nti",
        "--mode", "live",
        "--storage", "json",
        "--load-strategy", "full",
        "--output", str(tmp_path / "nti.json"),
    ])

    mode = validate_arguments(parser, args)

    scraper = create_scraper(args, mode)

    try:
        assert scraper.max_jobs is None
        assert scraper.max_pages is None

    finally:
        scraper.client.close()


def test_mapper_parse_reuse():

    html = """
    <html>
    <body>
    <h2>Prerequisites</h2>
    <p>Python and SQL</p>
    <h2>Duration</h2>
    <p>72 Hours</p>
    </body>
    </html>
    """

    soup = NTIMapper.clean_soup(html)

    assert (
        NTIMapper.extract_sections(html)
        ==
        NTIMapper.extract_sections(
            html, soup=soup
        )
    )

    assert (
        NTIMapper.extract_duration(html)
        ==
        NTIMapper.extract_duration(
            html, soup=soup
        )
    )
