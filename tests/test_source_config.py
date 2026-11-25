import pytest

from dataclasses import FrozenInstanceError

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