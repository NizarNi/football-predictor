import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests


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


# Odds API client tests
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
    mock_request.return_value = mock_response

    with pytest.raises(APIError) as exc:
        odds_api_client.get_odds_for_sport("soccer_epl")

    assert exc.value.code == "PARSE_ERROR"


# Elo client tests
@patch("football_predictor.elo_client.requests.get")
def test_elo_timeout_raises_apierror(mock_get):
    elo_client._elo_cache["data"] = None
    elo_client._elo_cache["timestamp"] = None
    mock_get.side_effect = requests.Timeout("Timeout occurred")

    with pytest.raises(APIError) as exc:
        elo_client.fetch_team_elo_ratings()

    assert exc.value.code == "TIMEOUT"


@patch("football_predictor.elo_client.csv.DictReader")
@patch("football_predictor.elo_client.requests.get")
def test_elo_invalid_response_raises_apierror(mock_get, mock_reader):
    elo_client._elo_cache["data"] = None
    elo_client._elo_cache["timestamp"] = None

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.text = "Club,Elo\nTeam,abc"
    mock_get.return_value = response
    mock_reader.side_effect = ValueError("Invalid CSV")

    with pytest.raises(APIError) as exc:
        elo_client.fetch_team_elo_ratings()

    assert exc.value.code == "PARSE_ERROR"


# xG data fetcher tests
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


# Understat client tests
@patch("football_predictor.understat_client.asyncio.wait_for")
def test_understat_timeout_raises_apierror(mock_wait_for):
    understat_client._standings_cache.clear()

    def _raise_timeout(coro, timeout):
        coro.close()
        raise asyncio.TimeoutError("Understat timeout")

    mock_wait_for.side_effect = _raise_timeout

    with pytest.raises(APIError) as exc:
        understat_client.fetch_understat_standings("PL")

    assert exc.value.code == "TIMEOUT"


def test_understat_invalid_response_raises_apierror():
    understat_client._standings_cache.clear()

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with patch("football_predictor.understat_client.aiohttp.ClientSession", return_value=DummySession()):
        with patch("football_predictor.understat_client.Understat") as mock_understat:
            understat_instance = MagicMock()
            understat_instance.get_teams = AsyncMock(side_effect=ValueError("Invalid JSON"))
            understat_instance.get_league_results = AsyncMock(return_value=[])
            mock_understat.return_value = understat_instance

            with pytest.raises(APIError) as exc:
                asyncio.run(understat_client._fetch_league_standings("PL"))

    assert exc.value.code == "PARSE_ERROR"
