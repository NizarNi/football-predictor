import pytest

from football_predictor.app import app, FuturesTimeoutError
from football_predictor.errors import APIError


@pytest.fixture
def client():
    app.testing = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_context_dependencies(monkeypatch):
    monkeypatch.setattr("football_predictor.app.get_current_season", lambda: 2024)
    monkeypatch.setattr(
        "football_predictor.understat_client.fetch_understat_standings",
        lambda league, season: [
            {"name": "Home Team", "position": 1, "points": 50, "form": "WWWWW"},
            {"name": "Away Team", "position": 2, "points": 48, "form": "WWLWD"},
        ],
    )
    monkeypatch.setattr(
        "football_predictor.elo_client.get_team_elo",
        lambda team, allow_network=True: 1500,
    )


def test_context_upstream_api_error(client, mock_context_dependencies, monkeypatch):
    def raise_api_error(*args, **kwargs):
        raise APIError("elo", "unavailable", "Elo service unavailable")

    monkeypatch.setattr(
        "football_predictor.elo_client.calculate_elo_probabilities",
        raise_api_error,
    )

    response = client.get(
        "/match/123/context",
        query_string={
            "league": "test_league",
            "home_team": "Home Team",
            "away_team": "Away Team",
        },
    )

    assert response.status_code == 502
    payload = response.get_json()
    assert payload["message"] == "Upstream API error"
    assert payload["error"]["source"] == "elo"
    assert "Elo service unavailable" in payload["error"]["detail"]


def test_context_timeout_returns_504(client, mock_context_dependencies, monkeypatch):
    monkeypatch.setattr(
        "football_predictor.elo_client.calculate_elo_probabilities",
        lambda home, away: {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
    )

    def trigger_timeout(*args, **kwargs):
        raise FuturesTimeoutError()

    monkeypatch.setattr("football_predictor.app.wait", trigger_timeout)

    response = client.get(
        "/match/456/context",
        query_string={
            "league": "test_league",
            "home_team": "Home Team",
            "away_team": "Away Team",
        },
    )

    assert response.status_code == 504
    payload = response.get_json()
    assert payload["message"] == "Context assembly timeout"
    assert payload["error"] is None
