import pytest

from unittest.mock import Mock

from scrapers.config import (
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    REQUEST_DELAY
)

from scrapers.source_config import SourceConfig
from scrapers.utils.http_client import HTTPClient


def test_http_client_default_settings():

    client = HTTPClient()

    try:
        assert client.request_timeout == REQUEST_TIMEOUT
        assert client.max_retries == MAX_RETRIES
        assert client.request_delay == REQUEST_DELAY

    finally:
        client.close()


def test_http_client_custom_settings():

    config = SourceConfig(
        base_url="https://example.com",
        request_timeout=60,
        max_retries=5,
        request_delay=10
    )

    client = HTTPClient(config)

    try:
        assert client.request_timeout == 60
        assert client.max_retries == 5
        assert client.request_delay == 10

    finally:
        client.close()


def test_http_client_retry_configuration():

    config = SourceConfig(
        base_url="https://example.com",
        max_retries=5
    )

    client = HTTPClient(config)

    try:
        adapter = client.session.get_adapter(
            "https://example.com"
        )

        assert adapter.max_retries.total == 5

    finally:
        client.close()


def test_http_client_request_settings(monkeypatch):

    config = SourceConfig(
        base_url="https://example.com",
        request_timeout=60,
        request_delay=10,
        enabled=True
    )

    client = HTTPClient(config)

    mock_wait = Mock()
    mock_get = Mock()

    monkeypatch.setattr(
        client.rate_limiter, "wait", mock_wait
    )

    monkeypatch.setattr(
        client.session, "get", mock_get
    )

    try:
        client.get("https://example.com")

        mock_wait.assert_called_once()

        assert client.rate_limiter.min_interval == 10

        assert mock_get.call_args.kwargs["timeout"] == 60

    finally:
        client.close()


def test_disabled_source_blocks_requests(monkeypatch):

    config = SourceConfig(
        base_url="https://example.com",
        enabled=False
    )

    client = HTTPClient(config)

    mock_get = Mock()
    mock_wait = Mock()

    monkeypatch.setattr(
        client.session, "get", mock_get
    )

    monkeypatch.setattr(
        client.rate_limiter, "wait", mock_wait
    )

    try:
        with pytest.raises(PermissionError):
            client.get("https://example.com")

        mock_get.assert_not_called()
        mock_wait.assert_not_called()

    finally:
        client.close()


def test_enabled_source_allows_requests(monkeypatch):

    config = SourceConfig(
        base_url="https://example.com",
        enabled=True
    )

    client = HTTPClient(config)

    mock_get = Mock()

    monkeypatch.setattr(
        client.session, "get", mock_get
    )

    try:
        client.get("https://example.com")

        mock_get.assert_called_once()

    finally:
        client.close()