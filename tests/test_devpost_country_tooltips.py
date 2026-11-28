
import pytest

from bs4 import BeautifulSoup

from scrapers.sources.devpost_mapper import (
    extract_eligibility,
    DevpostExcludedOpportunity,
    DevpostEligibilityUnverified,
)


def parse(html):

    return extract_eligibility(
        BeautifulSoup(html, "html.parser")
    )


def tooltip(kind, countries):

    prefix = (
        "Only specific"
        if kind == "allow"
        else "Specific"
    )

    label = (
        "countries/territories included"
        if kind == "allow"
        else "countries/territories excluded"
    )

    return (
        '<ul id="eligibility-list"><li>'
        + prefix
        + ' <span data-tooltip="" title="'
        + countries
        + '">'
        + label
        + '</span></li></ul>'
    )


def modal(kind, countries):

    title = (
        "Countries included"
        if kind == "allow"
        else "Countries excluded"
    )

    return (
        '<div id="eligibility-countries-modal-title">'
        + title
        + '</div>'
        + '<ul id="eligibility-countries-modal-list">'
        + "".join(
            "<li>" + country + "</li>"
            for country in countries
        )
        + '</ul>'
    )


def test_real_qnx_blocklist():

    result = parse(
        tooltip(
            "block",
            "Brazil, Crimea, Cuba, Iran Islamic Republic of, "
            "Korea Democratic People's Republic of, Russia"
        )
    )

    assert len(result["excluded_countries"]) == 6
    assert result["egypt_eligibility"] == "unverified"


@pytest.mark.parametrize(
    "country",
    ["Canada", "Bangladesh"]
)
def test_foreign_allowlist(country):

    with pytest.raises(
        DevpostExcludedOpportunity,
        match="Egypt not present"
    ):
        parse(tooltip("allow", country))


@pytest.mark.parametrize(
    "country",
    [
        "Egypt",
        "EGYPT",
        "Arab Republic of Egypt",
        "Egypt, Arab Republic of",
    ]
)
def test_egypt_blocklist(country):

    with pytest.raises(
        DevpostExcludedOpportunity,
        match="Egypt is explicitly excluded"
    ):
        parse(tooltip("block", country))


def test_egypt_allowlist():

    result = parse(
        tooltip("allow", "Egypt, Canada")
    )

    assert result["included_countries"] == [
        "Egypt", "Canada"
    ]


def test_egypt_comma_alias():

    result = parse(
        tooltip(
            "allow",
            "Egypt, Arab Republic of, Canada"
        )
    )

    assert result["included_countries"] == [
        "Egypt, Arab Republic of", "Canada"
    ]


@pytest.mark.parametrize(
    "countries",
    ["", " ", "Canada,,Russia", ",Canada"]
)
def test_invalid_tooltip(countries):

    with pytest.raises(
        DevpostEligibilityUnverified
    ):
        parse(tooltip("block", countries))


def test_matching_modal_and_tooltip():

    result = parse(
        tooltip("block", "Canada, Russia")
        + modal("block", ["Russia", "Canada"])
    )

    assert set(result["excluded_countries"]) == {
        "Canada", "Russia"
    }


def test_conflicting_country_lists():

    with pytest.raises(
        DevpostEligibilityUnverified,
        match="Conflicting country lists"
    ):
        parse(
            tooltip("block", "Canada")
            + modal("block", ["Egypt"])
        )


def test_conflicting_restriction_types():

    with pytest.raises(
        DevpostEligibilityUnverified,
        match="Conflicting country restrictions"
    ):
        parse(
            tooltip("allow", "Egypt")
            + modal("block", ["Canada"])
        )


def test_unrelated_tooltip_not_used():

    html = (
        '<ul id="eligibility-list">'
        '<li>Specific countries/territories excluded</li>'
        '<li><span data-tooltip="" title="Canada">'
        'Other information</span></li>'
        '</ul>'
    )

    with pytest.raises(
        DevpostEligibilityUnverified,
        match="Country blocklist unavailable"
    ):
        parse(html)


def test_standard_exceptions_unchanged():

    html = (
        '<ul id="eligibility-list"><li>'
        'All countries/territories, excluding '
        '<span data-tooltip="" title="Canada">'
        'standard exceptions</span>'
        '</li></ul>'
    )

    result = parse(html)

    assert result["egypt_eligibility"] == "unverified"
    assert result["listed_countries"] == []


def test_modal_only_preserved():

    result = parse(
        modal("allow", ["Egypt", "Canada"])
    )

    assert result["included_countries"] == [
        "Egypt", "Canada"
    ]
