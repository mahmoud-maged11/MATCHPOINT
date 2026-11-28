import pytest

from scrapers.sources.egyincs_mapper import EgyincsMapper


ARABIC_JOB = "".join(
    chr(value)
    for value in (0x0648, 0x0638, 0x064A, 0x0641, 0x0629)
)

ARABIC_INTERNSHIP = "".join(
    chr(value)
    for value in (0x062A, 0x062F, 0x0631, 0x064A, 0x0628)
)


def classify(title, slugs):

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
    )


@pytest.mark.parametrize(
    "title,slugs,expected",
    [
        (
            ARABIC_JOB + " Amazon Customer Service Associate",
            ["full-time", "student-internship", "job"],
            "job",
        ),
        (
            "Data Entry job at Aman Group",
            ["full-time"],
            "job",
        ),
        (
            "MCV Spare Parts Sales Eng Job",
            [],
            "job",
        ),
        (
            "Siemens HR Operations Working Student job",
            ["part-time", "student-internship", "job"],
            "job",
        ),
        (
            ARABIC_JOB + " Online Instructor at Almentor",
            [],
            "job",
        ),
        (
            "Emaar AR Safe Accountant Job",
            [],
            "job",
        ),
        (
            "Ibn Sina Administrative Assistant internship",
            ["internship", "job"],
            "internship",
        ),
        (
            "Informa Markets Investor Program Specialist Internship",
            ["internship", "student-internship", "job"],
            "internship",
        ),
        (
            "RATP Application Support Coordinator Job",
            ["full-time", "student-internship", "job"],
            "job",
        ),
        (
            ARABIC_INTERNSHIP + " Software Engineering",
            ["job", "internship"],
            "internship",
        ),
    ],
)
def test_observed_classification_cases(title, slugs, expected):

    assert classify(title, slugs) == expected


@pytest.mark.parametrize(
    "title,slugs",
    [
        ("Resala Training Centers RTC", []),
        ("New and Renewable Energy Authority", []),
        (
            "Motorola Solutions Egypt System Engineer",
            ["internship", "graduate-internship", "full-time", "job"],
        ),
        ("Software Engineer", ["job", "internship"]),
        ("Job and Internship Opportunities", ["job", "internship"]),
        ("Software Engineer", ["full-time"]),
        ("Job Opportunities", ["unrecognized-type"]),
        (
            ARABIC_JOB + " " + ARABIC_INTERNSHIP,
            ["job", "internship"],
        ),
    ],
)
def test_ambiguous_cases_remain_rejected(title, slugs):

    with pytest.raises(
        ValueError,
        match="Missing or ambiguous opportunity type",
    ):
        classify(title, slugs)


@pytest.mark.parametrize(
    "title,slugs,expected",
    [
        ("Software Engineer", ["job"], "job"),
        ("Software Internship", ["internship"], "internship"),
        ("Scholarship", ["scholarship"], "scholarship"),
        (
            "Graduate Development Program",
            ["internship"],
            "graduate_program",
        ),
        (
            "Software Consultant",
            ["job", "freelance"],
            "freelance",
        ),
    ],
)
def test_existing_classification_contract(title, slugs, expected):

    assert classify(title, slugs) == expected
