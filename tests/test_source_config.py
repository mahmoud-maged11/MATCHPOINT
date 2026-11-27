from dataclasses import FrozenInstanceError
from typing import get_args

import pytest

from scrapers.models import SourceName

from scrapers.source_config import (
    SourceConfig,
    get_source_config,
    SOURCE_CONFIGS
)

from scrapers.config import (
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    REQUEST_DELAY
)

from scrapers.source_config import (
    SourceConfig,
    get_source_config
)


def test_default_settings():

    config = SourceConfig(
        base_url="https://example.com"
    )

    assert config.request_timeout == REQUEST_TIMEOUT
    assert config.max_retries == MAX_RETRIES
    assert config.request_delay == REQUEST_DELAY
    assert config.enabled is False

def test_custom_settings():

    config = SourceConfig(
        base_url="https://example.com",
        request_timeout=60,
        max_retries=5,
        request_delay=10
    )

    assert config.request_timeout == 60
    assert config.max_retries == 5
    assert config.request_delay == 10


def test_wuzzuf_configuration():

    config = get_source_config("wuzzuf")

    assert config.base_url == "https://wuzzuf.net"
    assert config.enabled is True


def test_unknown_source():

    with pytest.raises(ValueError):
        get_source_config("unknown_source")


def test_configuration_is_immutable():

    config = get_source_config("wuzzuf")

    with pytest.raises(FrozenInstanceError):
        config.request_timeout = 100


EXPECTED_SOURCES = {
    "wuzzuf",
    "forasna",
    "egyincs",
    "itida",
    "nti",
    "bayt",
    "devpost",
    "un_volunteers"
}


def test_final_source_scope():

    assert set(SOURCE_CONFIGS) == EXPECTED_SOURCES


def test_model_source_scope():

    assert set(get_args(SourceName)) == EXPECTED_SOURCES


def test_model_and_config_consistency():

    assert set(get_args(SourceName)) == set(SOURCE_CONFIGS)


@pytest.mark.parametrize("source", sorted(EXPECTED_SOURCES))
def test_final_sources_enabled(source):

    assert get_source_config(source).enabled is True


@pytest.mark.parametrize(
    "source",
    ["amideast", "linkedin", "tanqeeb"]
)
def test_out_of_scope_sources_rejected(source):

    with pytest.raises(ValueError):
        get_source_config(source)