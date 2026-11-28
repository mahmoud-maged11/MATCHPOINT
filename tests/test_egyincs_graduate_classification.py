import pytest

from scrapers.sources.egyincs_mapper import EgyincsMapper


def classify(slugs, description, title="System Engineer"):

    terms = {
        "jobs-type": [
            {"slug": slug, "name": slug}
            for slug in slugs
        ]
    }

    return EgyincsMapper.extract_opportunity_type(
        terms,
        title,
        "jobs",
        description=description,
    )


GRADUATE_TAGS = [
    "job",
    "internship",
    "graduate-internship",
    "full-time",
]


@pytest.mark.parametrize(
    "description",
    [
        "Motorola Solutions Graduate Program",
        "Engineering Graduate Development Program",
        "Graduate Trainee Programme",
    ],
)
def test_explicit_graduate_program(description):

    assert classify(
        GRADUATE_TAGS,
        description,
    ) == "graduate_program"


@pytest.mark.parametrize(
    "description",
    [
        None,
        "",
        "Suitable for fresh graduates",
        "Bachelor degree required",
        "Graduate engineer with one year experience",
    ],
)
def test_ambiguous_description_rejected(description):

    with pytest.raises(ValueError):

        classify(GRADUATE_TAGS, description)


def test_generic_job_not_reclassified():

    assert classify(
        ["job"],
        "Our company also offers a Graduate Program",
    ) == "job"


def test_missing_graduate_taxonomy_rejected():

    with pytest.raises(ValueError):

        classify(
            ["job", "internship"],
            "Graduate Program",
        )


def test_conflicting_scholarship_rejected():

    with pytest.raises(ValueError):

        classify(
            GRADUATE_TAGS + ["scholarship"],
            "Graduate Program",
        )


def test_unknown_taxonomy_rejected():

    with pytest.raises(ValueError):

        classify(
            GRADUATE_TAGS + ["unknown-type"],
            "Graduate Program",
        )


def test_late_incidental_mention_rejected():

    with pytest.raises(ValueError):

        classify(
            GRADUATE_TAGS,
            "Other information. " * 100
            + "Graduate Program",
        )


def test_institution_page_not_classified():

    with pytest.raises(ValueError):

        classify(
            [],
            "We provide training and education services",
            title="Training Centers",
        )
