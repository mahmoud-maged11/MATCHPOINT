import pytest
import requests

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



def test_post_request_settings(monkeypatch):

    config = SourceConfig(
        base_url="https://example.com",
        request_timeout=60,
        request_delay=10,
        enabled=True
    )

    client = HTTPClient(config)

    response = Mock(status_code=200)
    mock_post = Mock(return_value=response)
    mock_wait = Mock()

    monkeypatch.setattr(
        client.session, "post", mock_post
    )

    monkeypatch.setattr(
        client.rate_limiter, "wait", mock_wait
    )

    try:
        result = client.post(
            "https://example.com",
            data={"page": "2"},
            headers={"Referer": "https://example.com"}
        )

        assert result is response

        mock_wait.assert_called_once()

        mock_post.assert_called_once_with(
            "https://example.com",
            data={"page": "2"},
            headers={"Referer": "https://example.com"},
            timeout=60,
            allow_redirects=False
        )

        response.raise_for_status.assert_called_once()

    finally:
        client.close()


def test_disabled_source_blocks_post(monkeypatch):

    config = SourceConfig(
        base_url="https://example.com",
        enabled=False
    )

    client = HTTPClient(config)

    mock_post = Mock()
    mock_wait = Mock()

    monkeypatch.setattr(
        client.session, "post", mock_post
    )

    monkeypatch.setattr(
        client.rate_limiter, "wait", mock_wait
    )

    try:
        with pytest.raises(PermissionError):
            client.post("https://example.com")

        mock_post.assert_not_called()
        mock_wait.assert_not_called()

    finally:
        client.close()


@pytest.mark.parametrize(
    "status_code",
    [301, 302, 303, 307, 308]
)
def test_post_rejects_redirects(
    monkeypatch, status_code
):

    client = HTTPClient()

    response = Mock(status_code=status_code)

    monkeypatch.setattr(
        client.session,
        "post",
        Mock(return_value=response)
    )

    monkeypatch.setattr(
        client.rate_limiter, "wait", Mock()
    )

    try:
        with pytest.raises(requests.HTTPError):
            client.post("https://example.com")

    finally:
        client.close()


def test_post_propagates_http_error(monkeypatch):

    client = HTTPClient()

    response = Mock(status_code=500)

    response.raise_for_status.side_effect = (
        requests.HTTPError("Server error")
    )

    monkeypatch.setattr(
        client.session,
        "post",
        Mock(return_value=response)
    )

    monkeypatch.setattr(
        client.rate_limiter, "wait", Mock()
    )

    try:
        with pytest.raises(requests.HTTPError):
            client.post("https://example.com")

    finally:
        client.close()


def test_post_propagates_timeout(monkeypatch):

    client = HTTPClient()

    monkeypatch.setattr(
        client.session,
        "post",
        Mock(side_effect=requests.Timeout("Timeout"))
    )

    monkeypatch.setattr(
        client.rate_limiter, "wait", Mock()
    )

    try:
        with pytest.raises(requests.Timeout):
            client.post("https://example.com")

    finally:
        client.close()


def test_post_retry_policy():

    client = HTTPClient()

    try:
        retry = client.session.get_adapter(
            "https://example.com"
        ).max_retries

        assert "GET" in retry.allowed_methods
        assert "POST" not in retry.allowed_methods

        assert retry.connect == 0
        assert retry.other == 0

        assert retry.is_retry("GET", 503)
        assert not retry.is_retry("POST", 503)

    finally:
        client.close()