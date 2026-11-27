from datetime import datetime, timezone

import pytest

from scrapers.sources.egyincs_mapper import EgyincsMapper


def make_term(taxonomy, slug, name=None):

    return {
        "taxonomy": taxonomy,
        "slug": slug,
        "name": name or slug,
    }


def make_record():

    return {
        "id": 12345,
        "status": "publish",
        "title": {
            "rendered": "Data Engineer &amp; Developer"
        },
        "content": {
            "rendered": "<p>Python and SQL</p>"
        },
        "link": "https://egyincs.com/opportunities/data-engineer/",
        "date_gmt": "2026-11-25T08:00:00",
        "felan-jobs_select_company": "100",
        "felan-jobs_apply_external": "https://example.com/apply",
        "felan-jobs_closing_date": "",
        "_embedded": {
            "wp:term": [
                [
                    make_term("jobs-type", "job"),
                    make_term("jobs-type", "full-time"),
                ],
                [
                    make_term("jobs-workplace", "remote"),
                ],
                [
                    make_term("jobs-career", "junior"),
                ],
                [
                    make_term("jobs-experience", "1-3"),
                ],
                [
                    make_term("jobs-skills", "python", "Python"),
                    make_term("jobs-skills", "sql", "SQL"),
                ],
                [
                    make_term("felan_location", "egypt", "Egypt"),
                ],
                [
                    make_term("felan_state", "cairo", "Cairo"),
                ],
                [
                    make_term(
                        "jobs-categories",
                        "technology",
                        "Technology",
                    ),
                ],
            ]
        },
    }


def set_types(record, *slugs):

    record["_embedded"]["wp:term"][0] = [
        make_term("jobs-type", slug)
        for slug in slugs
    ]


def test_basic_mapping():

    result = EgyincsMapper.map_record(
        make_record(),
        company_name="Test Company",
    )

    assert result.source_name == "egyincs"
    assert result.source_opportunity_id == "12345"
    assert result.title == "Data Engineer & Developer"
    assert result.organization == "Test Company"
    assert result.description == "Python and SQL"
    assert result.opportunity_type == "job"


def test_employment_types():

    result = EgyincsMapper.map_record(make_record())

    assert result.employment_types == ["full_time"]


def test_work_modes():

    result = EgyincsMapper.map_record(make_record())

    assert result.work_modes == ["remote"]


def test_location():

    result = EgyincsMapper.map_record(make_record())

    assert result.location == "Egypt, Cairo"


def test_required_skills():

    result = EgyincsMapper.map_record(make_record())

    assert result.required_skills == ["Python", "SQL"]


def test_categories():

    result = EgyincsMapper.map_record(make_record())

    assert result.categories == ["Technology"]


def test_experience():

    result = EgyincsMapper.map_record(make_record())

    assert result.experience_level == "junior"
    assert result.experience_years_min == 1
    assert result.experience_years_max == 3


def test_publication_date():

    result = EgyincsMapper.map_record(make_record())

    assert result.published_at == datetime(
        2026, 11, 25, 8, 0,
        tzinfo=timezone.utc,
    )

    assert result.published_at_precision == "exact"


def test_unknown_application_status():

    result = EgyincsMapper.map_record(make_record())

    assert result.status == "unknown"
    assert result.source_status_raw == "publish"
    assert result.deadline is None


def test_unverified_deadline():

    record = make_record()

    record["felan-jobs_closing_date"] = "2027-12-29"

    result = EgyincsMapper.map_record(record)

    assert result.deadline is None
    assert result.deadline_raw == "2027-12-29"


def test_external_application_url():

    result = EgyincsMapper.map_record(make_record())

    assert (
        result.raw_payload["application_url"]
        == "https://example.com/apply"
    )


@pytest.mark.parametrize(
    "slug, expected",
    [
        ("job", "job"),
        ("internship", "internship"),
        ("student-internship", "internship"),
        ("graduate-internship", "internship"),
        ("summer-internship", "internship"),
        ("winter-internship", "internship"),
        ("scholarship", "scholarship"),
        ("volunteer", "volunteering"),
        ("competition", "competition"),
        ("hackathon", "hackathon"),
        ("bootcamp", "training"),
        ("freelance", "freelance"),
        ("event", "event"),
    ],
)
def test_opportunity_types(slug, expected):

    record = make_record()

    set_types(record, slug)

    result = EgyincsMapper.map_record(record)

    assert result.opportunity_type == expected


def test_graduate_program():

    record = make_record()

    set_types(record, "graduate-internship")

    record["title"]["rendered"] = (
        "Graduate Development Program"
    )

    result = EgyincsMapper.map_record(record)

    assert result.opportunity_type == "graduate_program"


def test_freelance_priority():

    record = make_record()

    set_types(record, "job", "freelance")

    result = EgyincsMapper.map_record(record)

    assert result.opportunity_type == "freelance"


def test_ambiguous_opportunity_type():

    record = make_record()

    set_types(record, "job", "scholarship")

    with pytest.raises(ValueError):
        EgyincsMapper.map_record(record)


def test_unmapped_opportunity_type():

    record = make_record()

    set_types(record, "unrecognized-type")
    with pytest.raises(ValueError):
        EgyincsMapper.map_record(record)


def test_course_mapping():

    record = make_record()

    record["link"] = (
        "https://egyincs.com/courses/python-course/"
    )

    record["_embedded"]["wp:term"].append([
        make_term(
            "course_category",
            "programming",
            "Programming",
        )
    ])

    result = EgyincsMapper.map_record(
        record,
        endpoint="lp_course",
    )

    assert result.opportunity_type == "training"
    assert result.required_skills is None
    assert "Programming" in result.categories


def test_sensitive_fields_excluded():

    record = make_record()

    record["applicants"] = [
        {"email": "private@example.com"}
    ]

    record["author"] = 999

    result = EgyincsMapper.map_record(record)

    assert "applicants" not in result.raw_payload
    assert "author" not in result.raw_payload


def test_invalid_source_url():

    record = make_record()

    record["link"] = "https://example.com/opportunities/test/"

    with pytest.raises(ValueError):
        EgyincsMapper.map_record(record)


def test_missing_title():

    record = make_record()

    record["title"]["rendered"] = ""

    with pytest.raises(ValueError):
        EgyincsMapper.map_record(record)


def test_invalid_id():

    record = make_record()

    record["id"] = None

    with pytest.raises(ValueError):
        EgyincsMapper.map_record(record)


def test_unpublished_record():

    record = make_record()

    record["status"] = "draft"

    with pytest.raises(ValueError):
        EgyincsMapper.map_record(record)


def test_conflicting_experience_levels():

    record = make_record()

    record["_embedded"]["wp:term"][2].append(
        make_term("jobs-career", "senior")
    )

    result = EgyincsMapper.map_record(record)

    assert result.experience_level == "unknown"


def test_invalid_application_url():

    record = make_record()

    record["felan-jobs_apply_external"] = (
        "javascript:alert(1)"
    )

    result = EgyincsMapper.map_record(record)

    assert result.raw_payload["application_url"] is None


@pytest.mark.parametrize(
    "slugs, title, expected",
    [
        (
            [],
            "Retail Makeup Trainee",
            "internship",
        ),
        (
            ["graduate-internship"],
            "برنامج تدريب الخريجين Siemens Genesis",
            "graduate_program",
        ),
        (
            ["initiative", "remote"],
            "NTI AI Ambassadors Program",
            "training",
        ),
        (
            ["initiative"],
            "منحة مبادرة الرواد الرقميون",
            "scholarship",
        ),
        (
            ["bootcamp", "other"],
            "مؤتمر نيست جين",
            "event",
        ),
        (
            ["internship", "scholarship"],
            "منحة معسكر البرمجة المكثف",
            "scholarship",
        ),
    ],
)
def test_real_source_classification(slugs, title, expected):

    record = make_record()

    set_types(record, *slugs)

    record["title"]["rendered"] = title

    result = EgyincsMapper.map_record(record)

    assert result.opportunity_type == expected


def test_disclosed_salary():

    record = make_record()

    record.update({
        "felan-jobs_salary_show": "range",
        "felan-jobs_salary_minimum": "6700 ",
        "felan-jobs_salary_maximum": "8200 ",
        "felan-jobs_currency_type": "ج.م",
        "felan-jobs_salary_rate": "month",
    })

    result = EgyincsMapper.map_record(record)

    assert result.salary_min == 6700
    assert result.salary_max == 8200
    assert result.currency == "EGP"
    assert result.salary_period == "monthly"


def test_paid_internship_without_amount():

    record = make_record()

    record.update({
        "felan-jobs_salary_show": "paid_internship",
        "felan-jobs_salary_minimum": "0",
        "felan-jobs_salary_maximum": "0",
    })

    result = EgyincsMapper.map_record(record)

    assert result.salary_min is None
    assert result.salary_max is None


@pytest.mark.parametrize(
    "minimum, maximum",
    [
        ("NaN", "NaN"),
        ("Infinity", "Infinity"),
        ("", ""),
        ("0", "0"),
        ("9000", "5000"),
        ("-100", "-200"),
    ],
)
def test_invalid_salary_values(minimum, maximum):

    record = make_record()

    record.update({
        "felan-jobs_salary_show": "range",
        "felan-jobs_salary_minimum": minimum,
        "felan-jobs_salary_maximum": maximum,
    })

    result = EgyincsMapper.map_record(record)

    assert result.salary_min is None
    assert result.salary_max is None


@pytest.mark.parametrize(
    "slug, expected_min, expected_max",
    [
        ("0-exp", 0, None),
        ("10", 10, None),
        ("0-1", 0, 1),
    ],
)
def test_real_experience_ranges(
    slug,
    expected_min,
    expected_max,
):

    record = make_record()

    record["_embedded"]["wp:term"][3] = [
        make_term("jobs-experience", slug)
    ]

    result = EgyincsMapper.map_record(record)

    assert result.experience_years_min == expected_min
    assert result.experience_years_max == expected_max


def test_mid_level_source_slug():

    record = make_record()

    record["_embedded"]["wp:term"][2] = [
        make_term(
            "jobs-career",
            "experienced-mid-level",
        )
    ]

    result = EgyincsMapper.map_record(record)

    assert result.experience_level == "mid_level"