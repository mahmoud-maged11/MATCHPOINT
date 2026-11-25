import pytest

from datetime import datetime, timezone

from scrapers.sources.itida_mapper import ITIDAMapper


BASE = "https://itida.gov.eg"

PROGRAM_URL = (
    BASE + "/English/Programs/"
    "StudentSummerTraining/Pages/default.aspx"
)

EVENT_URL = (
    BASE + "/English/MediaCenter/"
    "Events/Pages/sample-event.aspx"
)

OBSERVED_AT = datetime(
    2026, 11, 25, 10, 0,
    tzinfo=timezone.utc
)


def make_program_html(
    title="Student Summer Training",
    content="Training for university students."
):

    return f"""
    <html>
        <main>
            <h1 class="briefHeader">{title}</h1>

            <div class="ms-rtestate-field">
                {content}
            </div>

            <div style="display:none;">
                <div class="ms-rtestate-field">
                    Unrelated ManageIT content
                </div>
            </div>
        </main>
    </html>
    """


def make_event_html(
    category="Workshop",
    start="20/11/2026",
    end="21/11/2026",
    title="AI Workshop"
):

    return f"""
    <html>
        <main>
            <div class="EventItemDev">
                <h4>{title}</h4>

                <div>Start Date: {start}</div>
                <div>End Date: {end}</div>
                <div>Location: Cairo</div>
                <div>Category: {category}</div>
            </div>

            <div class="innerPageContent">
                Learn practical AI skills.
            </div>
        </main>
    </html>
    """


def test_program_basic_mapping():

    result = ITIDAMapper.map_page(
        make_program_html(),
        PROGRAM_URL,
        OBSERVED_AT
    )

    assert result.source_name == "itida"
    assert result.source_opportunity_id == (
        "program:studentsummertraining"
    )
    assert result.title == "Student Summer Training"
    assert result.organization == "ITIDA"
    assert result.opportunity_type == "internship"
    assert result.status == "unknown"


def test_hidden_program_content_excluded():

    result = ITIDAMapper.map_page(
        make_program_html(),
        PROGRAM_URL,
        OBSERVED_AT
    )

    assert "ManageIT" not in result.description
    assert "Training for university students" in (
        result.description
    )


@pytest.mark.parametrize(
    "attribute",
    [
        'hidden',
        'aria-hidden="true"',
        'style="DISPLAY: NONE;"',
        'style="color:red; display:none;"'
    ]
)
def test_hidden_elements(attribute):

    html = f"""
    <main>
        <div {attribute}>Hidden content</div>
        <div>Visible content</div>
    </main>
    """

    soup = ITIDAMapper.clean_soup(html)

    assert "Hidden content" not in soup.get_text()
    assert "Visible content" in soup.get_text()


def test_program_closed_registration():

    html = make_program_html(
        content=(
            "Systel Program: Closed "
            "NTI programs Registration: Closed"
        )
    )

    result = ITIDAMapper.map_page(
        html, PROGRAM_URL, OBSERVED_AT
    )

    assert result.status == "closed"
    assert result.source_status_raw is not None


def test_partial_closed_registration():

    html = make_program_html(
        content="Systel Program: Closed"
    )

    result = ITIDAMapper.map_page(
        html, PROGRAM_URL, OBSERVED_AT
    )

    assert result.status == "unknown"


def test_program_requirements():

    html = make_program_html(
        content=(
            "Admission criteria: University students "
            "Registration: Apply online"
        )
    )

    result = ITIDAMapper.map_page(
        html, PROGRAM_URL, OBSERVED_AT
    )

    assert result.requirements == "University students"


def test_alternative_program_title():

    html = make_program_html().replace(
        "briefHeader", "mainTitle"
    )

    result = ITIDAMapper.map_page(
        html, PROGRAM_URL, OBSERVED_AT
    )

    assert result.title == "Student Summer Training"


def test_program_missing_title():

    with pytest.raises(ValueError):

        ITIDAMapper.map_page(
            make_program_html(title=""),
            PROGRAM_URL,
            OBSERVED_AT
        )


def test_event_basic_mapping():

    result = ITIDAMapper.map_page(
        make_event_html(),
        EVENT_URL,
        OBSERVED_AT
    )

    assert result.source_opportunity_id == (
        "event:sample-event"
    )
    assert result.title == "AI Workshop"
    assert result.opportunity_type == "training"
    assert result.location == "Cairo"
    assert result.categories == ["Workshop"]
    assert result.status == "expired"


@pytest.mark.parametrize(
    "category, expected",
    [
        ("Training", "training"),
        ("Workshop", "training"),
        ("Conference", "event"),
        ("Summit", "event"),
        ("Webinar", "event"),
        ("Employment Fair", "event"),
        ("Exhibition", "event"),
        ("Event", "event"),
        ("Matchmaking", "event")
    ]
)
def test_event_category_mapping(category, expected):

    result = ITIDAMapper.map_page(
        make_event_html(category=category),
        EVENT_URL,
        OBSERVED_AT
    )

    assert result.opportunity_type == expected


def test_future_event_status_unknown():

    result = ITIDAMapper.map_page(
        make_event_html(
            start="01/12/2026",
            end="02/12/2026"
        ),
        EVENT_URL,
        OBSERVED_AT
    )

    assert result.status == "unknown"


def test_event_ending_today():

    result = ITIDAMapper.map_page(
        make_event_html(
            start="24/11/2026",
            end="25/11/2026"
        ),
        EVENT_URL,
        OBSERVED_AT
    )

    assert result.status == "unknown"


def test_event_invalid_date_range():

    result = ITIDAMapper.map_page(
        make_event_html(
            start="24/11/2026",
            end="20/11/2026"
        ),
        EVENT_URL,
        OBSERVED_AT
    )

    assert result.status == "unknown"


def test_event_dates_not_application_deadline():

    result = ITIDAMapper.map_page(
        make_event_html(),
        EVENT_URL,
        OBSERVED_AT
    )

    assert result.deadline is None
    assert result.deadline_raw is None

    assert result.raw_payload["event_end_date"] == (
        "21/11/2026"
    )


def test_event_unknown_category():

    with pytest.raises(ValueError):

        ITIDAMapper.map_page(
            make_event_html(category="Unrecognized"),
            EVENT_URL,
            OBSERVED_AT
        )


def test_event_missing_description():

    html = make_event_html().replace(
        "Learn practical AI skills.", ""
    )

    with pytest.raises(ValueError):

        ITIDAMapper.map_page(
            html, EVENT_URL, OBSERVED_AT
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://itida.gov.eg/page.aspx",
        "https://example.com/page.aspx",
        "https://itida.gov.eg/page.html",
        "https://itida.gov.eg/English/Programs/Pages/default.aspx",
        "https://itida.gov.eg/English/MediaCenter/Events/Pages/default.aspx"
    ]
)
def test_invalid_source_url(url):

    with pytest.raises(ValueError):

        ITIDAMapper.map_page(
            make_program_html(),
            url,
            OBSERVED_AT
        )


def test_url_normalization():

    result = ITIDAMapper.normalize_url(
        EVENT_URL + "?tracking=123#section"
    )

    assert result == EVENT_URL


def test_case_insensitive_identity():

    page_type, slug = ITIDAMapper.extract_identity(
        PROGRAM_URL.lower()
    )

    assert page_type == "program"
    assert slug == "studentsummertraining"


def test_naive_observation_time_rejected():

    with pytest.raises(ValueError):

        ITIDAMapper.map_page(
            make_program_html(),
            PROGRAM_URL,
            datetime(2026, 11, 25)
        )


@pytest.mark.parametrize(
    "value",
    ["", None, "invalid", "31/02/2026"]
)
def test_invalid_event_date(value):

    assert ITIDAMapper.parse_event_date(value) is None




def test_nested_hidden_styles():

    html = """
    <main>
        <div style="display:none;">
            <div style="color:red;">
                Hidden child
            </div>

            <div style="display:none;">
                Nested hidden child
            </div>
        </div>

        <div style="color:blue;">
            Visible content
        </div>
    </main>
    """

    soup = ITIDAMapper.clean_soup(html)

    assert "Hidden child" not in soup.get_text()
    assert "Nested hidden child" not in soup.get_text()
    assert "Visible content" in soup.get_text()


def test_nested_hidden_attributes():

    html = """
    <main>
        <div hidden>
            <div hidden>
                Hidden child
            </div>

            <div aria-hidden="true">
                Another hidden child
            </div>

            <script>
                Hidden script
            </script>
        </div>

        <div>Visible content</div>
    </main>
    """

    soup = ITIDAMapper.clean_soup(html)

    assert "Hidden child" not in soup.get_text()
    assert "Another hidden child" not in soup.get_text()
    assert soup.select_one("script") is None
    assert "Visible content" in soup.get_text()