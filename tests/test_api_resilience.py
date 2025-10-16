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

from football_predictor import config
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

    def fake_request(method, url, timeout=None, **kwargs):
        call_counter["count"] += 1
        raise requests.exceptions.Timeout("simulated timeout")

    monkeypatch.setattr(odds_api_client._session, "request", fake_request)

    with pytest.raises(APIError) as exc:
        odds_api_client.get_available_sports()

    assert call_counter["count"] == config.API_MAX_RETRIES
    assert exc.value.code == "TIMEOUT"


def test_odds_api_recovers_after_server_error(monkeypatch, api_key_setup):
    responses = [
        MockResponse(status_code=500, reason="Server Error"),
        MockResponse(
            status_code=200,
            json_data={"sports": []},
            headers={"x-requests-remaining": "9", "x-requests-used": "1"},
        ),
    ]
    call_counter = {"count": 0}

    def fake_request(method, url, timeout=None, **kwargs):
        call_counter["count"] += 1
        return responses.pop(0)

    monkeypatch.setattr(odds_api_client._session, "request", fake_request)

    payload = odds_api_client.get_available_sports()

    assert call_counter["count"] == 2
    assert payload == {"sports": []}


def test_odds_api_permanent_server_error(monkeypatch, api_key_setup):
    responses = [MockResponse(status_code=503, reason="Service Unavailable") for _ in range(config.API_MAX_RETRIES)]
    call_counter = {"count": 0}

    def fake_request(method, url, timeout=None, **kwargs):
        call_counter["count"] += 1
        return responses[min(call_counter["count"] - 1, len(responses) - 1)]

    monkeypatch.setattr(odds_api_client._session, "request", fake_request)

    with pytest.raises(APIError) as exc:
        odds_api_client.get_available_sports()

    assert call_counter["count"] == config.API_MAX_RETRIES
    assert exc.value.code in {"NETWORK_ERROR", "HTTP_ERROR"}


def test_upcoming_route_returns_make_error_on_failure(monkeypatch):
    def raise_error(*args, **kwargs):
        raise APIError("OddsAPI", "NETWORK_ERROR", "The Odds API is temporarily unavailable.")

    monkeypatch.setattr(
        "football_predictor.app.get_upcoming_matches_with_odds", raise_error
    )

    client = flask_app.test_client()
    response = client.get("/upcoming")

    assert response.status_code == 200
    body = response.get_json()
    assert body == {
        "matches": [],
        "total_matches": 0,
        "source": "odds_unavailable",
        "warning": "odds_unavailable_for_league",
    }


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
