
import pytest

from scrapers.sources.egyincs_mapper import EgyincsMapper


def classify(slugs, title, description=None):
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


@pytest.mark.parametrize(
    "title,description",
    [
        (
            "Storekeeper - Student",
            "Practical internship program for Storekeeper Trainee",
        ),
        (
            "Maintenance Engineer",
            "\u0628\u0631\u0646\u0627\u0645\u062c "
            "\u062a\u062f\u0631\u064a\u0628 "
            "\u0639\u0645\u0644\u064a "
            "\u0645\u0647\u0646\u062f\u0633 "
            "\u062a\u062d\u062a "
            "\u0627\u0644\u062a\u062f\u0631\u064a\u0628",
        ),
        (
            "Production Engineer",
            "Practical internship program for Production Trainee",
        ),
    ],
)
def test_practical_internship(title, description):
    assert classify(
        ["job", "student-internship", "full-time"],
        title,
        description,
    ) == "internship"


def test_educational_simulation():
    assert classify(
        ["internship", "student-internship", "freelance"],
        "Bank Online Sessions",
        "Lectures and practical simulation",
    ) == "training"


@pytest.mark.parametrize(
    "slugs,title,description",
    [
        (
            [],
            "Training Centers",
            "Institutional services",
        ),
        (
            ["job", "internship", "student-internship"],
            "Company Internships & Jobs",
            "Multiple vacancies",
        ),
        (
            ["job", "student-internship"],
            "Storekeeper",
            "Students are welcome to apply",
        ),
        (
            ["job", "student-internship"],
            "Storekeeper",
            "Practical internship program",
        ),
        (
            ["job", "student-internship", "unrecognized-type"],
            "Storekeeper",
            "Practical internship program for Trainee",
        ),
        (
            ["internship", "freelance"],
            "Online Sessions",
            "Freelance assignments",
        ),
        (
            ["internship", "freelance"],
            "Online Sessions",
            "Lectures without practical activities",
        ),
    ],
)
def test_ambiguous_records_remain_rejected(
    slugs, title, description
):
    with pytest.raises(ValueError):
        classify(slugs, title, description)


def test_course_behavior_unchanged():
    assert EgyincsMapper.extract_opportunity_type(
        {},
        "Python Course",
        "lp_course",
    ) == "training"


def test_unambiguous_job_unchanged():
    assert classify(
        ["job", "full-time"],
        "Data Engineer",
    ) == "job"
