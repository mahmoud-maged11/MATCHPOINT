import json

from datetime import datetime, timezone

import pytest

from scrapers.sources.forasna_mapper import ForasnaMapper


URL = "https://forasna.com/job/p/test-job-12345"

OBSERVED_AT = datetime(
    2026, 11, 25, 12, 0,
    tzinfo=timezone.utc
)


def make_posting():

    return {
        "@type": "JobPosting",
        "identifier": {
            "name": "Forasna",
            "value": "12345"
        },
        "title": "مهندس بيانات",
        "description": "<p>Data Engineering Job</p>",
        "datePosted": "2026-11-25T09:00:00+02:00",
        "validThrough": "2026-12-25T09:00:00+02:00",
        "employmentType": "FULL_TIME",
        "hiringOrganization": {
            "name": "Test Company"
        },
        "jobLocation": {
            "address": {
                "addressLocality": "مدينة نصر",
                "addressRegion": "القاهرة",
                "addressCountry": "EG"
            }
        }
    }


def make_html(posting=None, fields=None, description=None,
              active=True):

    if posting is None:
        posting = make_posting()

    if fields is None:
        fields = {
            "مستوي الخبرة": "خبرة متوسطة",
            "سنين الخبرة": "5-\u200e7 سنوات خبرة",
            "المؤهل المطلوب": "مؤهل عالي",
            "نوع الوظيفة": "يوم كامل",
            "مجال الوظيفة": "تكنولوجيا المعلومات",
            "تخصص الوظيفة": "هندسة البيانات",
            "الراتب الأساسي": "الراتب غير معلن"
        }

    field_html = "".join(
        f"""
        <li>
            <p class="title-lable">
                <span>{key}</span>
            </p>
            <p class="item-info">{value}</p>
        </li>
        """
        for key, value in fields.items()
    )

    description_html = (
        f'<div class="job-more-info descri">'
        f'<p class="job-bio">{description}</p>'
        f'</div>'
        if description is not None
        else ""
    )

    button = (
        '<a class="apply-btn">تقدم للوظيفة</a>'
        if active else ""
    )

    return f"""
    <html>
        <script type="application/ld+json">
            {json.dumps(posting, ensure_ascii=False)}
        </script>
        <ul>{field_html}</ul>
        {description_html}
        {button}
    </html>
    """


def map_html(html):

    return ForasnaMapper.map_job(
        html,
        URL,
        observed_at=OBSERVED_AT
    )


def test_basic_mapping():

    result = map_html(make_html())

    assert result.source_name == "forasna"
    assert result.source_opportunity_id == "12345"
    assert result.title == "مهندس بيانات"
    assert result.organization == "Test Company"
    assert result.opportunity_type == "job"
    assert result.status == "active"


def test_location():

    result = map_html(make_html())

    assert result.location == "مدينة نصر, القاهرة, EG"


def test_experience():

    result = map_html(make_html())

    assert result.experience_level == "mid_level"
    assert result.experience_years_min == 5
    assert result.experience_years_max == 7


def test_exact_dates():

    result = map_html(make_html())

    assert result.published_at == datetime(
        2026, 11, 25, 7, 0,
        tzinfo=timezone.utc
    )

    assert result.published_at_precision == "exact"
    assert result.deadline_precision == "exact"


def test_expired_job():

    posting = make_posting()

    posting["validThrough"] = (
        "2026-11-24T09:00:00+02:00"
    )

    result = map_html(make_html(posting=posting))

    assert result.status == "expired"


def test_unknown_status():

    result = map_html(make_html(active=False))

    assert result.status == "unknown"


def test_employment_type():

    result = map_html(make_html())

    assert result.employment_types == ["full_time"]


def test_internship():

    result = map_html(
        make_html(fields={"نوع الوظيفة": "تدريب"})
    )

    assert result.opportunity_type == "internship"


def test_freelance():

    result = map_html(
        make_html(fields={"نوع الوظيفة": "عمل حر"})
    )

    assert result.opportunity_type == "freelance"


def test_remote():

    result = map_html(
        make_html(fields={"نوع الوظيفة": "عمل من المنزل"})
    )

    assert result.work_modes == ["remote"]
    assert result.opportunity_type == "job"


def test_undisclosed_salary():

    result = map_html(make_html())

    assert result.salary_min is None
    assert result.salary_max is None
    assert result.currency is None


def test_zero_salary():

    result = map_html(
        make_html(
            fields={
                "الراتب الأساسي": "0 - 0 جنيه مصري"
            }
        )
    )

    assert result.salary_min is None
    assert result.salary_max is None


def test_html_salary():

    result = map_html(
        make_html(
            fields={
                "الراتب الأساسي": "5000 - 8000 جنيه مصري"
            }
        )
    )

    assert result.salary_min == 5000
    assert result.salary_max == 8000
    assert result.currency == "EGP"


def test_json_ld_salary():

    posting = make_posting()

    posting["baseSalary"] = {
        "currency": "EGP",
        "value": {
            "minValue": 10000,
            "maxValue": 15000,
            "unitText": "MONTH"
        }
    }

    result = map_html(
        make_html(posting=posting, fields={})
    )

    assert result.salary_min == 10000
    assert result.salary_max == 15000
    assert result.salary_period == "monthly"


def test_description_html_priority():

    result = map_html(
        make_html(description="وصف الوظيفة")
    )

    assert result.description == "وصف الوظيفة"


def test_description_json_ld_fallback():

    result = map_html(make_html())

    assert result.description == "Data Engineering Job"


def test_categories():

    result = map_html(make_html())

    assert result.categories == [
        "تكنولوجيا المعلومات",
        "هندسة البيانات"
    ]


def test_sensitive_fields_excluded():

    result = map_html(
        make_html(
            fields={
                "الجنس المطلوب": "ذكر",
                "السن المطلوب": "25 - 35",
                "المؤهل المطلوب": "مؤهل عالي"
            }
        )
    )

    fields = result.raw_payload["fields"]

    assert "الجنس المطلوب" not in fields
    assert "السن المطلوب" not in fields


def test_id_mismatch():

    posting = make_posting()
    posting["identifier"]["value"] = "99999"

    with pytest.raises(ValueError):
        map_html(make_html(posting=posting))


def test_missing_job_posting():

    with pytest.raises(ValueError):
        map_html("<html></html>")


def test_external_url_rejected():

    with pytest.raises(ValueError):

        ForasnaMapper.map_job(
            make_html(),
            "https://example.com/job/p/test-12345"
        )


def test_missing_title():

    posting = make_posting()
    posting.pop("title")

    with pytest.raises(ValueError):
        map_html(make_html(posting=posting))

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("سنتان-\u200e10 سنوات خبرة", (2, 10)),
        ("سنة خبرة على الأقل", (1, None)),
        ("5 سنوات خبرة على الأكثر", (None, 5)),
        ("سنتين خبرة على الأقل", (2, None)),
        ("٣ - ٥ سنوات خبرة", (3, 5)),
        ("لا يشترط", (0, None)),
        ("بدون خبرة", (0, None)),
        ("أكثر من 3 سنوات", (3, None)),
        ("أقل من 5 سنوات", (None, 5)),
        ("7 - 3 سنوات", (None, None)),
        ("خبرة غير محددة", (None, None)),
        (None, (None, None)),
    ]
)
def test_arabic_experience_years(raw, expected):

    assert (
        ForasnaMapper.extract_experience_years(raw)
        == expected
    )


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("مدير / مشرف", "manager"),
        ("طالب", "entry_level"),
        ("لا يشترط", "entry_level"),
    ]
)
def test_additional_experience_levels(raw, expected):

    result = map_html(
        make_html(
            fields={"مستوي الخبرة": raw}
        )
    )

    assert result.experience_level == expected


def test_json_ld_internship():

    posting = make_posting()
    posting["employmentType"] = "INTERN"

    result = map_html(
        make_html(posting=posting, fields={})
    )

    assert result.opportunity_type == "internship"
    assert result.employment_types is None


def test_internship_with_full_time():

    posting = make_posting()
    posting["employmentType"] = "FULL_TIME"

    result = map_html(
        make_html(
            posting=posting,
            fields={"نوع الوظيفة": "تدريب"}
        )
    )

    assert result.opportunity_type == "internship"
    assert result.employment_types == ["full_time"]