import asyncio
import sys
import types
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest
import requests

# ---- Stubs to satisfy optional imports in code paths ----
if "aiohttp" not in sys.modules:
    aiohttp_stub = types.ModuleType("aiohttp")

    class _StubClientError(Exception):
        pass

    class _StubClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    aiohttp_stub.ClientError = _StubClientError
    aiohttp_stub.ClientSession = _StubClientSession
    sys.modules["aiohttp"] = aiohttp_stub

if "understat" not in sys.modules:
    understat_stub = types.ModuleType("understat")

    class _StubUnderstat:
        def __init__(self, session):
            self.session = session

        async def get_teams(self, *args, **kwargs):
            return []

        async def get_league_results(self, *args, **kwargs):
            return []

    understat_stub.Understat = _StubUnderstat
    sys.modules["understat"] = understat_stub

if "soccerdata" not in sys.modules:
    soccerdata_stub = types.ModuleType("soccerdata")

    class _StubFBref:
        def __init__(self, *args, **kwargs):
            pass

    soccerdata_stub.FBref = _StubFBref
    sys.modules["soccerdata"] = soccerdata_stub

if "pandas" not in sys.modules:
    pandas_stub = types.ModuleType("pandas")

    def _notna(value):
        return value is not None

    pandas_stub.notna = _notna
    pandas_stub.DataFrame = type("DataFrame", (), {})
    pandas_stub.Series = type("Series", (), {})
    sys.modules["pandas"] = pandas_stub

from football_predictor.errors import APIError
from football_predictor import elo_client, odds_api_client, understat_client, xg_data_fetcher


# -----------------------
# Odds API client tests
# -----------------------
@patch("football_predictor.odds_api_client.request_with_retries")
def test_timeout_raises_apierror(mock_request):
    odds_api_client.API_KEYS = ["test_key"]
    odds_api_client.invalid_keys.clear()
    odds_api_client.current_key_index = 0
    mock_request.side_effect = requests.Timeout("Simulated timeout")

    with pytest.raises(APIError) as exc:
        odds_api_client.get_odds_for_sport("soccer_epl")

    assert exc.value.code == "TIMEOUT"
    assert "OddsAPI" in exc.value.source


@patch("football_predictor.odds_api_client.request_with_retries")
def test_network_error_raises_apierror(mock_request):
    odds_api_client.API_KEYS = ["test_key"]
    odds_api_client.invalid_keys.clear()
    odds_api_client.current_key_index = 0
    mock_request.side_effect = requests.RequestException("Connection aborted")

    with pytest.raises(APIError) as exc:
        odds_api_client.get_odds_for_sport("soccer_epl")

    assert exc.value.code == "NETWORK_ERROR"


@patch("football_predictor.odds_api_client.request_with_retries")
def test_invalid_json_raises_apierror(mock_request):
    odds_api_client.API_KEYS = ["test_key"]
    odds_api_client.invalid_keys.clear()
    odds_api_client.current_key_index = 0

    mock_response = MagicMock()
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_response.headers = {}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response

    with pytest.raises(APIError) as exc:
        odds_api_client.get_odds_for_sport("soccer_epl")

    assert exc.value.code == "PARSE_ERROR"


# -----------------------
# Elo client tests (T7 uses request_with_retries now)
# -----------------------
@patch("football_predictor.elo_client.request_with_retries")
def test_elo_timeout_raises_apierror(mock_req):
    elo_client._elo_cache["data"] = None
    elo_client._elo_cache["timestamp"] = None
    mock_req.side_effect = requests.Timeout("Timeout occurred")

    with pytest.raises(APIError) as exc:
        elo_client.fetch_team_elo_ratings()

    assert exc.value.code == "TIMEOUT"


@patch("football_predictor.elo_client.request_with_retries")
@patch("football_predictor.elo_client.csv.DictReader")
def test_elo_invalid_response_raises_apierror(mock_reader, mock_req):
    elo_client._elo_cache["data"] = None
    elo_client._elo_cache["timestamp"] = None

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.text = "Club,Elo\nTeam,abc"
    mock_req.return_value = response
    mock_reader.side_effect = ValueError("Invalid CSV")

    with pytest.raises(APIError) as exc:
        elo_client.fetch_team_elo_ratings()

    assert exc.value.code == "PARSE_ERROR"


# -----------------------
# xG data fetcher tests
# -----------------------
def test_xg_timeout_raises_apierror():
    def _timeout_call(*args, **kwargs):
        raise requests.exceptions.Timeout("Timeout while fetching")

    with pytest.raises(APIError) as exc:
        xg_data_fetcher._safe_soccerdata_call(_timeout_call, "Fetch xG")

    assert exc.value.code == "TIMEOUT"


def test_xg_invalid_response_raises_apierror():
    def _invalid_call(*args, **kwargs):
        raise ValueError("Invalid JSON")

    with pytest.raises(APIError) as exc:
        xg_data_fetcher._safe_soccerdata_call(_invalid_call, "Fetch xG")

    assert exc.value.code == "PARSE_ERROR"


# -----------------------
# Understat client helpers & tests
# -----------------------
def _sample_understat_payloads():
    teams_payload = {
        "teams": [
            {
                "title": "Team A",
                "history": [
                    {
                        "xG": 1.2,
                        "xGA": 0.8,
                        "npxG": 1.1,
                        "npxGA": 0.6,
                        "ppda": {"att": 100, "def": 10},
                        "ppda_allowed": {"att": 90, "def": 9},
                    },
                    {
                        "xG": 1.8,
                        "xGA": 0.7,
                        "npxG": 1.5,
                        "npxGA": 0.5,
                        "ppda": {"att": 95, "def": 9},
                        "ppda_allowed": {"att": 85, "def": 8},
                    },
                ],
            },
            {
                "title": "Team B",
                "history": [
                    {
                        "xG": 0.9,
                        "xGA": 1.4,
                        "npxG": 0.7,
                        "npxGA": 1.1,
                        "ppda": {"att": 110, "def": 11},
                        "ppda_allowed": {"att": 88, "def": 11},
                    },
                    {
                        "xG": 1.0,
                        "xGA": 1.3,
                        "npxG": 0.8,
                        "npxGA": 1.0,
                        "ppda": {"att": 108, "def": 12},
                        "ppda_allowed": {"att": 92, "def": 10},
                    },
                ],
            },
        ]
    }

    fixtures_payload = {
        "fixtures": [
            {
                "isResult": True,
                "h": {"title": "Team A"},
                "a": {"title": "Team B"},
                "goals": {"h": 2, "a": 1},
                "forecast": {"w": 0.55, "d": 0.25, "l": 0.2},
                "xG": {"h": 1.9, "a": 0.8},
            },
            {
                "isResult": True,
                "h": {"title": "Team B"},
                "a": {"title": "Team A"},
                "goals": {"h": 1, "a": 1},
                "forecast": {"w": 0.35, "d": 0.4, "l": 0.25},
                "xG": {"h": 1.1, "a": 1.2},
            },
        ]
    }

    return teams_payload, fixtures_payload


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.reason = "OK"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)

    def json(self):
        return self._payload


@patch("football_predictor.understat_client.request_with_retries")
def test_understat_timeout_raises_apierror(mock_request):
    understat_client._standings_cache.clear()
    mock_request.side_effect = requests.Timeout("Understat timeout")

    with pytest.raises(APIError) as exc:
        understat_client.fetch_understat_standings("PL")

    assert exc.value.code == "TIMEOUT"


@patch("football_predictor.understat_client.request_with_retries")
def test_understat_invalid_response_raises_apierror(mock_request):
    understat_client._standings_cache.clear()

    class BadResponse:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("Invalid JSON")

    mock_request.return_value = BadResponse()

    with pytest.raises(APIError) as exc:
        understat_client.fetch_understat_standings("PL")

    assert exc.value.code == "PARSE_ERROR"


@patch("football_predictor.understat_client.request_with_retries")
def test_understat_retries_on_server_errors(mock_request):
    """We can’t simulate internal retry here, but we assert the intended kwargs are passed."""
    understat_client._standings_cache.clear()
    teams_payload, fixtures_payload = _sample_understat_payloads()
    call_contexts: List[str] = []

    def _fake_request(*, method, url, timeout, retries, backoff_factor, status_forcelist, logger, context, params=None, **kw):
        # capture contexts and assert retry config
        call_contexts.append(context)
        assert retries == 3
        assert 502 in status_forcelist
        # return teams first, fixtures second based on context
        if "teams" in context:
            return _FakeResponse(teams_payload)
        return _FakeResponse(fixtures_payload)

    mock_request.side_effect = _fake_request

    standings = understat_client.fetch_understat_standings("PL")
    assert len(standings) == 2
    # contexts we expect (order not strictly enforced across HTTP libs, but both should be present)
    assert any("teams" in c for c in call_contexts)
    assert any("results" in c for c in call_contexts)
    assert standings[0]["name"] == "Team A"


@patch("football_predictor.understat_client.request_with_retries")
def test_understat_rate_limit_raises_apierror(mock_request):
    understat_client._standings_cache.clear()

    class _RateLimitResponse(_FakeResponse):
        def __init__(self):
            super().__init__({}, status_code=429)

        def raise_for_status(self):
            raise requests.HTTPError("429", response=self)

    mock_request.return_value = _RateLimitResponse()

    with pytest.raises(APIError) as exc:
        understat_client.fetch_understat_standings("PL")

    assert exc.value.code == "429"
    assert exc.value.details == "rate_limited"
