import logging
from typing import Any, Dict

import pytest

from football_predictor.adapters import sportmonks


class _StubResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if 400 <= self.status_code:
            from requests import HTTPError

            raise HTTPError(f"status={self.status_code}")

    def json(self) -> Dict[str, Any]:
        return self._payload


class _StubSession:
    def __init__(self, response: _StubResponse) -> None:
        self._response = response

    def get(self, url: str, params: Dict[str, Any] | None = None, timeout: float | None = None) -> _StubResponse:
        return self._response


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sportmonks, "_cache", sportmonks._TTL())


@pytest.fixture(autouse=True)
def _force_league(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sportmonks, "sportmonks_league_id", lambda code: 999)
    monkeypatch.setattr(sportmonks, "SPORTMONKS_KEY", "token")


@pytest.mark.parametrize(
    "status_code,payload,expected,log_prefix",
    [
        (404, {}, [], "sportmonks_fixtures_empty"),
        (200, {"data": []}, [], None),
    ],
)
def test_get_fixtures_handles_responses(
    status_code: int,
    payload: Dict[str, Any],
    expected: list[Any],
    log_prefix: str | None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)

    response = _StubResponse(status_code=status_code, payload=payload)
    session = _StubSession(response)
    monkeypatch.setattr(sportmonks, "_session", lambda: session)

    adapter = sportmonks.SportmonksAdapter()
    fixtures = adapter.get_fixtures("EPL", "2024-03-01T00:00:00Z", "2024-03-02T00:00:00Z")

    assert fixtures == expected

    if log_prefix:
        assert any(log_prefix in record.message for record in caplog.records)
    else:
        assert all("sportmonks_fixtures_empty" not in record.message for record in caplog.records)
