import pytest
import requests

from football_predictor import elo_client, net_retry, understat_client
from football_predictor.errors import APIError


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def request(self, method, url, timeout=None, **kwargs):
        self.calls += 1
        if not self._responses:
            raise AssertionError("No more responses configured")
        return self._responses.pop(0)


def make_response(status_code, body="", url="http://api.clubelo.com/test"):
    response = requests.Response()
    response.status_code = status_code
    response.reason = "OK" if status_code == 200 else "Error"
    response._content = body.encode("utf-8")
    response.encoding = "utf-8"
    response.url = url
    return response


class FakeJSONResponse:
    def __init__(self, status_code, payload=None, url="http://understat.test/api"):
        self.status_code = status_code
        self.reason = "OK" if status_code < 400 else "Error"
        self._payload = payload
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"{self.status_code} Server Error: {self.reason}",
                response=self,
            )

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON payload configured")
        return self._payload


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("football_predictor.utils.time.sleep", lambda _duration: None)


def test_elo_retry_eventually_succeeds(monkeypatch):
    responses = [
        make_response(502),
        make_response(502),
        make_response(200, "Club,Elo\nTeam A,1500\n"),
    ]
    fake_session = FakeSession(responses)

    net_retry._get_session.cache_clear()
    monkeypatch.setattr(elo_client, "_REQUEST_FACADE_SESSION", fake_session)
    monkeypatch.setattr(elo_client, "_elo_cache", {"data": None, "timestamp": None})

    data = elo_client.fetch_team_elo_ratings()

    assert fake_session.calls == 3
    assert data["Team A"] == 1500.0


def test_elo_retry_rate_limited(monkeypatch):
    responses = [make_response(429), make_response(429), make_response(429)]
    fake_session = FakeSession(responses)

    net_retry._get_session.cache_clear()
    monkeypatch.setattr(elo_client, "_REQUEST_FACADE_SESSION", fake_session)
    monkeypatch.setattr(elo_client, "_elo_cache", {"data": None, "timestamp": None})

    with pytest.raises(APIError) as excinfo:
        elo_client.fetch_team_elo_ratings()

    assert excinfo.value.code == "429"
    assert excinfo.value.details == "rate_limited"


def test_understat_retry_eventually_succeeds(monkeypatch):
    history = [
        {
            "xG": 1.2,
            "xGA": 0.9,
            "npxG": 1.0,
            "npxGA": 0.8,
            "ppda": {"att": 10, "def": 5},
            "ppda_allowed": {"att": 12, "def": 6},
        }
        for _ in range(3)
    ]
    teams_payload = {
        "teams": [
            {"title": "Team A", "history": history},
            {"title": "Team B", "history": history},
        ]
    }
    results_payload = {
        "results": [
            {
                "isResult": True,
                "h": {"title": "Team A"},
                "a": {"title": "Team B"},
                "goals": {"h": 2, "a": 1},
                "forecast": {"w": 0.6, "d": 0.2, "l": 0.2},
                "xG": {"h": 1.1, "a": 0.9},
            },
            {
                "isResult": True,
                "h": {"title": "Team B"},
                "a": {"title": "Team A"},
                "goals": {"h": 1, "a": 1},
                "forecast": {"w": 0.3, "d": 0.4, "l": 0.3},
                "xG": {"h": 0.9, "a": 1.0},
            },
        ]
    }

    payload_iter = iter([teams_payload, results_payload])
    captured_kwargs: list[dict] = []

    def _fake_request_with_retries(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return FakeJSONResponse(200, next(payload_iter))

    monkeypatch.setattr(understat_client, "request_with_retries", _fake_request_with_retries)
    monkeypatch.setattr(understat_client, "_standings_cache", {})

    result = understat_client.fetch_understat_standings("Premier League", season=2023)

    assert len(captured_kwargs) == 2
    assert all(
        kwargs["retries"] == understat_client._RETRY_ATTEMPTS for kwargs in captured_kwargs
    )
    assert all(502 in kwargs["status_forcelist"] for kwargs in captured_kwargs)
    assert all(kwargs["params"]["league"] == "epl" for kwargs in captured_kwargs)
    assert any(team["name"] == "Team A" for team in result)


def test_understat_retry_rate_limited(monkeypatch):
    def _fake_request_with_retries(*args, **kwargs):
        response = requests.Response()
        response.status_code = 429
        response.url = "https://understat.test/api"
        raise requests.HTTPError("429 Too Many Requests", response=response)

    monkeypatch.setattr(understat_client, "request_with_retries", _fake_request_with_retries)
    monkeypatch.setattr(understat_client, "_standings_cache", {})

    with pytest.raises(APIError) as excinfo:
        understat_client.fetch_understat_standings("EPL", season=2023)

    assert excinfo.value.code == "429"
    assert excinfo.value.details == "rate_limited"
