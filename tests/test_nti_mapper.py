
import pytest

from scrapers.sources.nti_mapper import NTIMapper


BASE_URL = "https://www.nti.sci.eg"

UPSKILLING_HTML = """
<h1>Machine Learning - Module Details</h1>

<div>
    <h3>Module Name: Machine Learning (72 Hours)</h3>
</div>

<div>
    <h3>Technical Part Duration: 60 Hours.</h3>
</div>

<div>
    <h3>Module Description</h3>
    <ul><li>Learn machine learning techniques.</li></ul>
</div>

<div>
    <h3>Target Audience</h3>
    <ul><li>University graduates.</li></ul>
</div>

<div>
    <h3>Module Prerequisite</h3>
    <ul>
        <li>Basic Python Programming.</li>
        <li>Basic Mathematics.</li>
    </ul>
</div>

<div>
    <h3>Module Contents</h3>
    <ul>
        <li>Linear Regression.</li>
        <li>Neural Networks.</li>
    </ul>
</div>

<div>
    <h3>Module Name: Business Skills</h3>
    <h3>Duration: 12 Hours</h3>
</div>
"""

HIRE_READY_HTML = """
<h1>Cloud DevOps Accelerator <span>Code: D001</span></h1>
<h2>Part 1: Technical Program - Duration: 294 Hours.</h2>
<h3>Overview:</h3>
<ul><li>Cloud infrastructure training.</li></ul>
<h3>Prerequisites:</h3>
<ul><li>CCNA.</li><li>Linux Fundamentals.</li></ul>
<h3>Contents:</h3>
<ul><li>Kubernetes.</li><li>Terraform.</li></ul>
"""

CAREER_HTML = """
<h2>Part 2: Career development - Duration: 126 Hours.</h2>
<h3>Overview:</h3>
<ul><li>Professional development.</li></ul>
"""

CREATIVA_HTML = """
<h1>Machine Learning for Data Analysis (120 Hours)</h1>

<h2>Part 1 Technical Part (90 Hours)</h2>
<h3>Scope:</h3>
<ul><li>Applied machine learning.</li></ul>

<h3>Target Audience:</h3>
<ul><li>Computer Science graduates.</li></ul>

<h3>Prerequisites:</h3>
<ul>
    <li>Programming knowledge - optional.</li>
    <li>Basic mathematics - optional.</li>
</ul>

<h3>Content:</h3>
<ul><li>TensorFlow.</li></ul>

<h2>Part 2: Landing Your Freelance Job (30 Hours)</h2>

<h3>Target Audience:</h3>
<ul><li>University students.</li></ul>

<h3>Prerequisite:</h3>
<ul><li>Basic Computer Literacy.</li></ul>
"""


def make_listing(**overrides):

    listing = {
        "initiative": "upskilling",
        "track_id": "2581",
        "title": "Machine Learning",
        "category": "AI and IoT",
        "center_id": None,
        "location": None,
        "closed": True,
        "status_raw": "Registration closed for this track",
        "source_url": (
            BASE_URL + "/dey/coursesev.php?catID=202"
        ),
    }

    listing.update(overrides)

    return listing


def test_basic_mapping():

    result = NTIMapper.map_course(
        make_listing(), UPSKILLING_HTML
    )

    assert result.source_name == "nti"
    assert result.source_opportunity_id == "upskilling:2581"
    assert result.title == "Machine Learning"
    assert result.organization == "NTI"
    assert result.opportunity_type == "training"
    assert result.status == "closed"


def test_upskilling_duration():

    result = NTIMapper.map_course(
        make_listing(), UPSKILLING_HTML
    )

    durations = result.raw_payload["durations"]

    assert durations["total_hours"] == 72
    assert durations["technical_hours"] == 60
    assert durations["business_hours"] == 12


def test_required_skills():

    result = NTIMapper.map_course(
        make_listing(), UPSKILLING_HTML
    )

    assert result.required_skills == [
        "Basic Python Programming.",
        "Basic Mathematics.",
    ]


def test_curriculum_not_required_skills():

    result = NTIMapper.map_course(
        make_listing(), UPSKILLING_HTML
    )

    assert "Linear Regression." not in result.required_skills
    assert "Neural Networks." not in result.required_skills


def test_target_audience():

    result = NTIMapper.map_course(
        make_listing(), UPSKILLING_HTML
    )

    assert "University graduates." in result.requirements


def test_categories():

    result = NTIMapper.map_course(
        make_listing(), UPSKILLING_HTML
    )

    assert result.categories == [
        "Upskilling Programs", "AI and IoT"
    ]


def test_unknown_registration():

    result = NTIMapper.map_course(
        make_listing(closed=False, status_raw=None),
        UPSKILLING_HTML,
    )

    assert result.status == "unknown"
    assert result.source_status_raw is None


def test_closed_registration_evidence():

    result = NTIMapper.map_course(
        make_listing(), UPSKILLING_HTML
    )

    assert result.source_status_raw == (
        "Registration closed for this track"
    )


def test_hire_ready_duration():

    result = NTIMapper.map_course(
        make_listing(
            initiative="hire_ready",
            track_id="5301",
            title="Cloud DevOps Accelerator",
        ),
        HIRE_READY_HTML,
        career_html=CAREER_HTML,
    )

    durations = result.raw_payload["durations"]

    assert durations["technical_hours"] == 294
    assert durations["career_hours"] == 126
    assert durations["total_hours"] == 420


def test_creativa_duration():

    result = NTIMapper.map_course(
        make_listing(
            initiative="creativa",
            track_id="8102",
            center_id="13",
            location="Giza",
        ),
        CREATIVA_HTML,
    )

    durations = result.raw_payload["durations"]

    assert durations["total_hours"] == 120
    assert durations["technical_hours"] == 90
    assert durations["freelance_hours"] == 30


def test_optional_prerequisites():

    result = NTIMapper.map_course(
        make_listing(
            initiative="creativa",
            track_id="8102",
            center_id="13",
        ),
        CREATIVA_HTML,
    )

    assert result.required_skills == [
        "Basic Computer Literacy."
    ]

    optional = result.raw_payload["prerequisites"]["optional"]

    assert len(optional) == 2
    assert "Programming knowledge - optional." in optional


@pytest.mark.parametrize(
    "placeholder",
    ["NA", "N/A", "None", "Not applicable"],
)
def test_explicit_no_prerequisites(placeholder):

    html = """
    <h1>Big Data Essentials</h1>
    <h3>Module Description</h3>
    <ul><li>Introduction to big data.</li></ul>
    <h3>Module Prerequisites</h3>
    <ul><li>{}</li></ul>
    """.format(placeholder)

    result = NTIMapper.map_course(
        make_listing(track_id="2711"), html
    )

    assert result.required_skills == []
    assert result.raw_payload["prerequisites"]["explicit_none"]


def test_missing_prerequisites():

    html = """
    <h1>Sample Course</h1>
    <h3>Overview:</h3>
    <ul><li>Training program.</li></ul>
    """

    result = NTIMapper.map_course(make_listing(), html)

    assert result.required_skills is None


def test_creativa_identity():

    result = NTIMapper.map_course(
        make_listing(
            initiative="creativa",
            track_id="8102",
            center_id="13",
            location="Giza",
        ),
        CREATIVA_HTML,
    )

    assert result.source_opportunity_id == (
        "creativa:8102:center:13"
    )

    assert result.location == "Giza"


def test_different_centers_have_different_ids():

    first = NTIMapper.map_course(
        make_listing(
            initiative="creativa",
            center_id="13",
        ),
        CREATIVA_HTML,
    )

    second = NTIMapper.map_course(
        make_listing(
            initiative="creativa",
            center_id="14",
        ),
        CREATIVA_HTML,
    )

    assert first.source_opportunity_id != (
        second.source_opportunity_id
    )


def test_missing_deadline_and_salary():

    result = NTIMapper.map_course(
        make_listing(), UPSKILLING_HTML
    )

    assert result.deadline is None
    assert result.published_at is None
    assert result.salary_min is None
    assert result.salary_max is None


@pytest.mark.parametrize(
    "track_id",
    ["0", "-1", "", "abc", "../123"],
)
def test_invalid_track_id(track_id):

    with pytest.raises(ValueError):

        NTIMapper.map_course(
            make_listing(track_id=track_id),
            UPSKILLING_HTML,
        )


def test_invalid_initiative():

    with pytest.raises(ValueError):

        NTIMapper.map_course(
            make_listing(initiative="unsupported"),
            UPSKILLING_HTML,
        )


def test_missing_title():

    with pytest.raises(ValueError):

        NTIMapper.map_course(
            make_listing(title=" "),
            UPSKILLING_HTML,
        )


def test_missing_detail_heading():

    with pytest.raises(ValueError):

        NTIMapper.map_course(
            make_listing(),
            "<p>Invalid detail page</p>",
        )


def test_empty_detail_sections():

    with pytest.raises(ValueError):

        NTIMapper.map_course(
            make_listing(),
            "<h1>Course</h1><h3>Overview</h3>",
        )


def test_clean_text():

    assert NTIMapper.clean_text(
        " Machine \n Learning \t "
    ) == "Machine Learning"


def test_scripts_removed():

    soup = NTIMapper.clean_soup(
        "<script>ignored</script><h1>Course</h1>"
    )

    assert soup.find("script") is None
    assert soup.find("h1") is not None


def test_recommended_prerequisite_is_optional():

    html = """
    <h1>Motion Graphics</h1>
    <h3>Overview</h3>
    <ul><li>Motion design training.</li></ul>
    <h3>Prerequisites</h3>
    <ul>
        <li>Basic Adobe Photoshop knowledge.</li>
        <li>Understanding of design is recommended.</li>
    </ul>
    """

    result = NTIMapper.map_course(make_listing(), html)

    assert result.required_skills == [
        "Basic Adobe Photoshop knowledge."
    ]

    assert result.raw_payload["prerequisites"]["optional"] == [
        "Understanding of design is recommended."
    ]


def test_no_prerequisites_intro_is_not_skill():

    html = """
    <h1>CCNA v7</h1>
    <h3>Module Description</h3>
    <ul><li>Networking fundamentals.</li></ul>
    <h3>Module Prerequisites</h3>
    <p>There are no prerequisites for this course.
    Learners are expected to have the following skills:</p>
    <ul>
        <li>Basic computer literacy.</li>
        <li>Basic internet usage skills.</li>
    </ul>
    """

    result = NTIMapper.map_course(make_listing(), html)

    assert result.required_skills == [
        "Basic computer literacy.",
        "Basic internet usage skills.",
    ]

    prerequisites = result.raw_payload["prerequisites"]

    assert prerequisites["explicit_none"] is True
    assert len(prerequisites["notes"]) == 1

    assert "Prerequisite notes:" in result.requirements


def test_no_prerequisites_sentence():

    html = """
    <h1>Sample Course</h1>
    <h3>Overview</h3>
    <ul><li>Training program.</li></ul>
    <h3>Prerequisites</h3>
    <p>There are no prerequisites for this course.</p>
    """

    result = NTIMapper.map_course(make_listing(), html)

    assert result.required_skills == []
    assert result.raw_payload["prerequisites"]["explicit_none"]


def test_prerequisite_intro_is_note():

    sections = [{
        "part": None,
        "heading": "Prerequisites",
        "items": [
            "Learners are expected to have the following skills:",
            "Basic Python.",
        ],
    }]

    result = NTIMapper.extract_prerequisites(sections)

    assert result["required"] == ["Basic Python."]
    assert len(result["notes"]) == 1


def test_not_optional_is_required():

    sections = [{
        "part": None,
        "heading": "Prerequisites",
        "items": [
            "Python knowledge is not optional.",
        ],
    }]

    result = NTIMapper.extract_prerequisites(sections)

    assert len(result["required"]) == 1
    assert result["optional"] == []


def test_technical_word_in_course_title():

    html = """
    <h1>IT Technical Support Bootcamp (72 Hours)</h1>
    <h3>Technical Part Duration: 60 Hours</h3>
    <h3>Module Name: Business Skills</h3>
    <h3>Duration: 12 Hours</h3>
    """

    durations = NTIMapper.extract_duration(html)

    assert durations["total_hours"] == 72
    assert durations["technical_hours"] == 60
    assert durations["business_hours"] == 12


def test_technical_word_in_module_name():

    html = """
    <h3>Module Name: Technical Support (72 Hours)</h3>
    <h3>Technical Module Duration: 60 Hours</h3>
    <h3>Module Name: Business Skills</h3>
    <h3>Duration: 12 Hours</h3>
    """

    durations = NTIMapper.extract_duration(html)

    assert durations["total_hours"] == 72
    assert durations["technical_hours"] == 60
    assert durations["business_hours"] == 12
