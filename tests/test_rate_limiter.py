import pytest

from unittest.mock import Mock

from scrapers.utils.rate_limiter import RateLimiter


def test_negative_interval():

    with pytest.raises(ValueError):
        RateLimiter(-1)


def test_first_request_no_wait(monkeypatch):

    limiter = RateLimiter(2)

    mock_sleep = Mock()

    monkeypatch.setattr(
        "scrapers.utils.rate_limiter.time.sleep",
        mock_sleep
    )

    limiter.wait()

    mock_sleep.assert_not_called()


def test_wait_remaining_interval(monkeypatch):

    limiter = RateLimiter(2)

    limiter.last_request_time = 10

    mock_sleep = Mock()

    monkeypatch.setattr(
        "scrapers.utils.rate_limiter.time.monotonic",
        Mock(side_effect=[10.5, 12])
    )

    monkeypatch.setattr(
        "scrapers.utils.rate_limiter.time.sleep",
        mock_sleep
    )

    limiter.wait()

    mock_sleep.assert_called_once_with(1.5)

    assert limiter.last_request_time == 12


def test_no_wait_after_interval(monkeypatch):

    limiter = RateLimiter(2)

    limiter.last_request_time = 10

    mock_sleep = Mock()

    monkeypatch.setattr(
        "scrapers.utils.rate_limiter.time.monotonic",
        Mock(return_value=13)
    )

    monkeypatch.setattr(
        "scrapers.utils.rate_limiter.time.sleep",
        mock_sleep
    )

    limiter.wait()

    mock_sleep.assert_not_called()


def test_zero_interval(monkeypatch):

    limiter = RateLimiter(0)

    mock_sleep = Mock()

    monkeypatch.setattr(
        "scrapers.utils.rate_limiter.time.sleep",
        mock_sleep
    )

    limiter.wait()
    limiter.wait()

    mock_sleep.assert_not_called()