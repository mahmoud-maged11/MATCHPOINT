
import pytest

from bs4 import BeautifulSoup

from scrapers.sources.bayt import BaytScraper
from scrapers.sources.bayt_mapper import BaytMapper


@pytest.mark.parametrize(
    "value",
    [0, -1, True, False, 1.5, "10"],
)
@pytest.mark.parametrize(
    "attribute",
    ["max_jobs", "max_pages"],
)
def test_strict_limits(attribute, value):

    with pytest.raises(ValueError):
        BaytScraper(**{attribute: value})


def test_unlimited_limits():

    instance = BaytScraper(
        max_jobs=None,
        max_pages=None,
    )

    try:

        assert instance.max_jobs is None
        assert instance.max_pages is None

    finally:

        instance.client.close()


@pytest.mark.parametrize(
    "structured,description,expected",
    [
        (
            "TELECOMMUTE",
            "A full-time, hybrid position based in Cairo.",
            ["hybrid"],
        ),
        (
            None,
            "Ability to work in a hybrid model.",
            ["hybrid"],
        ),
        (
            None,
            "Employment Type: Full-Time (Hybrid - office visits)",
            ["hybrid"],
        ),
        (
            "TELECOMMUTE",
            "A fully office-based role.",
            None,
        ),
        (
            "TELECOMMUTE",
            "Build data pipelines.",
            ["remote"],
        ),
        (
            None,
            "Experience with hybrid cloud systems.",
            None,
        ),
        (
            None,
            "A fully office-based role.",
            ["on_site"],
        ),
        (
            None,
            "A hybrid position and a fully office-based role.",
            None,
        ),
    ],
)
def test_work_mode_evidence(
    structured, description, expected
):

    modes, evidence = BaytMapper.resolve_work_modes(
        {"jobLocationType": structured},
        description,
    )

    assert modes == expected


def test_listing_parse_reuse():

    html = """
    <html>
    <body>
        <a href="/en/egypt/jobs/data-engineer-1234567/">
            Data Engineer
        </a>
        <a href="/en/egypt/jobs/?page=2">
            Next
        </a>
    </body>
    </html>
    """

    soup = BeautifulSoup(
        html, "html.parser"
    )

    assert (
        BaytScraper.extract_jobs_with_diagnostics(html)
        ==
        BaytScraper.extract_jobs_with_diagnostics(
            html, soup=soup
        )
    )

    assert (
        BaytScraper.extract_next_page_with_diagnostics(
            html, 1
        )
        ==
        BaytScraper.extract_next_page_with_diagnostics(
            html, 1, soup=soup
        )
    )


@pytest.mark.parametrize(
    "source",
    ["bayt", "nti"],
)
def test_production_full_mode(source, tmp_path):

    from scrapers.main import (
        build_parser,
        validate_arguments,
        create_scraper,
    )

    parser = build_parser()

    args = parser.parse_args([
        "--source", source,
        "--mode", "live",
        "--storage", "json",
        "--load-strategy", "full",
        "--output", str(tmp_path / "output.json"),
    ])

    mode = validate_arguments(parser, args)

    instance = create_scraper(args, mode)

    try:

        assert instance.max_jobs is None
        assert instance.max_pages is None

    finally:

        instance.client.close()
