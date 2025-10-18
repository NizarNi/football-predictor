import sys
import types

import pytest
import requests

if "soccerdata" not in sys.modules:
    soccerdata_stub = types.ModuleType("soccerdata")

    class _PlaceholderFBref:  # pragma: no cover - only used when library missing
        def __init__(self, *args, **kwargs):
            raise RuntimeError("soccerdata stub in tests")

    soccerdata_stub.FBref = _PlaceholderFBref
    sys.modules["soccerdata"] = soccerdata_stub

if "pandas" not in sys.modules:
    sys.modules["pandas"] = types.ModuleType("pandas")

from football_predictor import odds_api_client
from football_predictor import xg_data_fetcher
from football_predictor.errors import APIError
from football_predictor.app import app as flask_app


class MockResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, reason="OK"):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}
        self.reason = reason

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if 400 <= self.status_code:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} Error", response=self
            )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("football_predictor.utils.time.sleep", lambda *_: None)


@pytest.fixture
def api_key_setup(monkeypatch):
    monkeypatch.setattr(odds_api_client, "API_KEYS", ["test-key"])
    odds_api_client.invalid_keys = set()
    odds_api_client.current_key_index = 0


def test_odds_api_retries_on_timeout(monkeypatch, api_key_setup):
    call_counter = {"count": 0}

    def fake_fetch(url, params=None, timeout=None, **kwargs):
        call_counter["count"] += 1
        raise APIError("OddsAPI", "TIMEOUT", "Odds API retry limit exceeded")

    monkeypatch.setattr(odds_api_client, "fetch_odds_with_backoff", fake_fetch)

    with pytest.raises(APIError) as exc:
        odds_api_client.get_available_sports()

    assert call_counter["count"] == 1
    assert exc.value.code == "TIMEOUT"
    assert exc.value.message == "The Odds API did not respond in time."


def test_odds_api_recovers_after_server_error(monkeypatch, api_key_setup):
    captured = {}

    def fake_fetch(url, params=None, timeout=None, **kwargs):
        response = MockResponse(
            status_code=200,
            json_data={"sports": []},
            headers={"x-requests-remaining": "9", "x-requests-used": "1"},
        )
        captured["response"] = response
        return response, 2

    monkeypatch.setattr(odds_api_client, "fetch_odds_with_backoff", fake_fetch)

    payload = odds_api_client.get_available_sports()

    assert payload == {"sports": []}
    assert getattr(captured["response"], "_odds_backoff_attempts") == 2


def test_odds_api_permanent_server_error(monkeypatch, api_key_setup):
    call_counter = {"count": 0}

    def fake_fetch(url, params=None, timeout=None, **kwargs):
        call_counter["count"] += 1
        raise APIError(
            "OddsAPI",
            "NETWORK_ERROR",
            "Odds API retry limit exceeded",
            details="apiKey=SECRET",
        )

    monkeypatch.setattr(odds_api_client, "fetch_odds_with_backoff", fake_fetch)

    with pytest.raises(APIError) as exc:
        odds_api_client.get_available_sports()

    assert call_counter["count"] == 1
    assert exc.value.code == "NETWORK_ERROR"
    assert exc.value.details == "apiKey=***"


def test_upcoming_route_returns_make_error_on_failure(monkeypatch):
    def raise_error(*args, **kwargs):
        raise APIError("OddsAPI", "NETWORK_ERROR", "The Odds API is temporarily unavailable.")

    monkeypatch.setattr(
        "football_predictor.app.get_upcoming_matches_with_odds", raise_error
    )

    client = flask_app.test_client()
    response = client.get("/upcoming")

    assert response.status_code == 503
    body = response.get_json()
    assert body["error"]
    assert body["message"]


def test_upcoming_skips_elo_after_timeout(monkeypatch):
    monkeypatch.setattr("football_predictor.app._recent_elo", {})
    monkeypatch.setattr("football_predictor.app._recent_match_elo", {})

    from football_predictor import elo_client

    monkeypatch.setattr(elo_client, "_ELO_UNHEALTHY_UNTIL", None, raising=False)

    matches = [
        {
            "event_id": f"match-{idx}",
            "id": f"legacy-{idx}",
            "commence_time": "2024-01-01T12:00:00Z",
            "home_team": f"Team {idx}A",
            "away_team": f"Team {idx}B",
            "bookmakers": [],
        }
        for idx in range(5)
    ]

    monkeypatch.setattr(
        "football_predictor.app.get_upcoming_matches_with_odds",
        lambda **_: [match.copy() for match in matches],
    )

    monkeypatch.setattr(
        "football_predictor.app.calculate_predictions_from_odds",
        lambda match: {
            "prediction": "home",
            "confidence": 75,
            "probabilities": {"home": 0.5, "draw": 0.3, "away": 0.2},
            "best_odds": {"home": 2.0},
            "arbitrage": None,
            "bookmaker_count": 1,
        },
    )

    call_count = {"count": 0}

    def failing_get_team_elo(team_name, allow_network=True):
        call_count["count"] += 1
        if call_count["count"] == 1:
            elo_client._mark_elo_unhealthy()
            raise APIError("EloAPI", "TIMEOUT", "timeout")
        return None

    monkeypatch.setattr("football_predictor.elo_client.get_team_elo", failing_get_team_elo)

    client = flask_app.test_client()
    response = client.get("/upcoming")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_matches"] == len(matches)
    assert all("elo_predictions" not in m for m in payload["matches"])
    assert call_count["count"] == 1


def test_xg_fetcher_wraps_request_exceptions(monkeypatch):
    monkeypatch.setattr(xg_data_fetcher, "load_from_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(xg_data_fetcher, "save_to_cache", lambda *args, **kwargs: None)

    class FakeFBref:
        def __init__(self, *args, **kwargs):
            self.session = requests.Session()

        def read_team_season_stats(self, **kwargs):
            raise requests.exceptions.Timeout("fbref timeout")

    monkeypatch.setattr(xg_data_fetcher.sd, "FBref", FakeFBref)

    with pytest.raises(APIError):
        xg_data_fetcher.fetch_league_xg_stats("PL", season=2024)
