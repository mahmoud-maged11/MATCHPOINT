
import pytest

from scrapers.sources.itida_mapper import ITIDAMapper

from test_itida_mapper import (
    make_event_html,
    EVENT_URL,
    OBSERVED_AT,
)


@pytest.mark.parametrize(
    "category, expected",
    [
        ("Exams", "event"),
        ("Conference Events", "event"),
        ("Summit Events", "event"),
    ],
)
def test_recovered_event_taxonomy(category, expected):

    result = ITIDAMapper.map_page(
        make_event_html(category=category),
        EVENT_URL,
        OBSERVED_AT,
    )

    assert result.opportunity_type == expected
    assert result.categories == [category]
    assert result.deadline is None
    assert result.deadline_raw is None


def test_exam_placeholder_not_invented():

    html = make_event_html(
        category="Exams"
    ).replace(
        "Learn practical AI skills.",
        "Read More",
    )

    result = ITIDAMapper.map_page(
        html,
        EVENT_URL,
        OBSERVED_AT,
    )

    assert result.description is None
    assert result.raw_payload["description"] == "Read More"


def test_generic_program_event_remains_unsupported():

    with pytest.raises(
        ValueError,
        match="Unsupported event category",
    ):

        ITIDAMapper.map_page(
            make_event_html(category="Programs"),
            EVENT_URL,
            OBSERVED_AT,
        )


def test_graduation_program_supported():

    assert (
        ITIDAMapper.PROGRAM_TYPES["graduation"]
        == "training"
    )


@pytest.mark.parametrize(
    "slug",
    [
        "export-it",
        "ngo",
        "industry-outlook",
        "talent-landscape",
        "business-environment",
        "government-support",
    ],
)
def test_non_individual_program_not_admitted(slug):

    assert slug not in ITIDAMapper.PROGRAM_TYPES
