import pytest

from football_predictor import app as app_module
from football_predictor import xg_data_fetcher


@pytest.fixture
def client():
    app_module.app.testing = True
    with app_module.app.test_client() as client:
        yield client


def test_xg_ready_payload_contains_rolling_arrays(client, monkeypatch):
    ready_payload = {
        "refresh_status": "ready",
        "availability": "available",
        "fast_path": False,
        "completeness": "season_plus_rolling",
        "season": {
            "home_stats": {"xg_for_per_game": 1.45, "xg_against_per_game": 0.98},
            "away_stats": {"xg_for_per_game": 0.88, "xg_against_per_game": 1.12},
        },
        "home_stats": {"recent_matches": [{"xg_for": 1.2, "xg_against": 0.7}]},
        "away_stats": {"recent_matches": [{"xg_for": 0.8, "xg_against": 1.0}]},
        "rolling_xg_home": {"for": [1.2], "against": [0.7], "dates": ["2024-08-01"], "window_len": 1},
        "rolling_xg_away": {"for": [0.8], "against": [1.0], "dates": ["2024-08-01"], "window_len": 1},
        "meta": {"league": "ENG-Premier League", "updated_at": "2024-09-01T00:00:00Z"},
    }

    monkeypatch.setattr(xg_data_fetcher, "canonicalize_league", lambda s: "ENG-Premier League")
    monkeypatch.setattr(app_module, "get_context_xg", lambda *a, **k: ready_payload)

    response = client.get(
        "/match/sample/xg",
        query_string={
            "home_team": "Chelsea",
            "away_team": "Arsenal",
            "league": "PL",
        },
    )

    assert response.status_code == 200
    data = response.get_json()

    assert data["refresh_status"] == "ready"
    assert data["availability"] == "available"
    assert data["home_stats"]["recent_matches"]
    assert data["away_stats"]["recent_matches"]
    assert data["meta"]["league"] == "ENG-Premier League"


def test_league_aliases_supported():
    for alias in ("PL", "ENG", "Premier League", "ENG-Premier League"):
        assert xg_data_fetcher.canonicalize_league(alias) == "ENG-Premier League"
