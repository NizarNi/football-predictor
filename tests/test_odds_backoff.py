import pytest

from football_predictor import odds_api_client


class DummyResp:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


def test_retry_on_500(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return DummyResp(500)
        return DummyResp(200)

    monkeypatch.setattr(odds_api_client.requests, "get", fake_get)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_BASE_DELAY", 0.01)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_JITTER", 0.0)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_MAX_ATTEMPTS", 3)

    sleeps = []
    monkeypatch.setattr(odds_api_client.time, "sleep", sleeps.append)

    response, attempts = odds_api_client.fetch_odds_with_backoff("fakeurl")

    assert response.status_code == 200
    assert calls["n"] == 3
    assert attempts == 3
    assert pytest.approx(sum(sleeps), rel=1e-3) == 0.03


def test_respects_retry_after(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return DummyResp(503, {"Retry-After": "0.1"})
        return DummyResp(200)

    monkeypatch.setattr(odds_api_client.requests, "get", fake_get)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_BASE_DELAY", 0.01)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_JITTER", 0.0)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_MAX_ATTEMPTS", 3)

    recorded_sleeps = []

    def fake_sleep(delay):
        recorded_sleeps.append(delay)

    monkeypatch.setattr(odds_api_client.time, "sleep", fake_sleep)

    odds_api_client.fetch_odds_with_backoff("fakeurl")

    assert calls["n"] == 2
    assert recorded_sleeps == [pytest.approx(0.1, rel=1e-3)]


def test_respects_retry_after_http_date(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    dt = datetime.now(timezone.utc) + timedelta(seconds=1)
    http_date = format_datetime(dt)

    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] > 1:
            return DummyResp(200)
        return DummyResp(503, {"Retry-After": http_date})

    monkeypatch.setattr(odds_api_client.requests, "get", fake_get)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_BASE_DELAY", 0.01)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_JITTER", 0.0)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_MAX_ATTEMPTS", 3)

    recorded_sleeps = []

    def fake_sleep(delay):
        recorded_sleeps.append(delay)

    monkeypatch.setattr(odds_api_client.time, "sleep", fake_sleep)

    response, attempts = odds_api_client.fetch_odds_with_backoff("fakeurl")

    assert response.status_code == 200
    assert attempts == 2
    assert len(recorded_sleeps) == 1
    assert recorded_sleeps[0] <= odds_api_client.MAX_RETRY_AFTER
    assert recorded_sleeps[0] >= 0.1


def test_retry_delay_capped(monkeypatch):
    def fake_get(url, headers=None, params=None, timeout=None):
        return DummyResp(503, {"Retry-After": "999"})

    monkeypatch.setattr(odds_api_client.requests, "get", fake_get)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_BASE_DELAY", 0.01)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_JITTER", 0.0)
    monkeypatch.setattr(odds_api_client.config_module, "ODDS_MAX_ATTEMPTS", 1)

    recorded_sleeps = []

    def fake_sleep(delay):
        recorded_sleeps.append(delay)

    monkeypatch.setattr(odds_api_client.time, "sleep", fake_sleep)

    with pytest.raises(odds_api_client.APIError):
        odds_api_client.fetch_odds_with_backoff("fakeurl")

    # With only one attempt, sleep should not be called, but ensure cap logic is respected
    # by calling the helper directly
    delay = odds_api_client._get_retry_delay(1, DummyResp(503, {"Retry-After": "999"}))
    assert delay == odds_api_client.MAX_RETRY_AFTER
