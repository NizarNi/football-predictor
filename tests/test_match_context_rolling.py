from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta

import pytest

sys.modules.setdefault("pandas", types.ModuleType("pandas"))
sys.modules.setdefault("soccerdata", types.ModuleType("soccerdata"))

from football_predictor import app as app_module
from football_predictor import xg_data_fetcher


def _sample_team_stats(xg_for_per_game: float, xg_against_per_game: float) -> dict:
    return {
        "xg_for_per_game": xg_for_per_game,
        "xg_against_per_game": xg_against_per_game,
        "scoring_clinicality": 0.0,
        "rolling_5": {},
        "form": None,
        "recent_matches": [],
        "using_rolling": False,
        "xg_for": xg_for_per_game * 10,
        "xg_against": xg_against_per_game * 10,
        "ps_xg_against": xg_against_per_game * 10,
        "matches_played": 10,
        "goals_for": xg_for_per_game * 10,
        "goals_against": xg_against_per_game * 10,
        "ps_xg_against_per_game": xg_against_per_game,
        "goals_for_per_game": xg_for_per_game,
        "goals_against_per_game": xg_against_per_game,
        "ps_xg_performance": 0.0,
    }


@pytest.fixture
def client():
    app_module.app.testing = True
    with app_module.app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def mock_xg_dependencies(monkeypatch):
    home_logs = [
        {
            "date": datetime(2024, 9, 21) - timedelta(days=7 * idx),
            "xg_for": 1.5 + idx * 0.1,
            "xg_against": 1.0 + idx * 0.05,
            "is_home": True,
            "opponent": f"Opponent {idx}",
            "result": "W",
        }
        for idx in range(3)
    ]
    away_logs = [
        {
            "date": datetime(2024, 9, 20) - timedelta(days=7 * idx),
            "xg_for": 1.4 + idx * 0.05,
            "xg_against": 1.2 + idx * 0.04,
            "is_home": False,
            "opponent": f"Rival {idx}",
            "result": "D" if idx % 2 else "L",
        }
        for idx in range(3)
    ]

    monkeypatch.setattr(
        xg_data_fetcher,
        "_resolve_fbref_team_name",
        lambda name, context=None: name,
    )
    monkeypatch.setattr(
        xg_data_fetcher,
        "fetch_league_xg_stats",
        lambda league, season=None, cache_only=False: {
            "Manchester United": _sample_team_stats(1.8, 1.1),
            "Brighton & Hove Albion": _sample_team_stats(1.6, 1.3),
        },
    )

    def fake_logs(league, season, team):
        if team == "Manchester United":
            return list(home_logs)
        if team == "Brighton & Hove Albion":
            return list(away_logs)
        return []

    monkeypatch.setattr(xg_data_fetcher, "_get_cached_team_logs_in_memory", fake_logs)
    monkeypatch.setattr(xg_data_fetcher, "_refresh_logs_async", lambda *args, **kwargs: "ready")
    xg_data_fetcher._PARTIAL_WINDOW_WARNINGS.clear()


def test_match_context_rolling_arrays_and_logs(client):
    response = client.get(
        "/match/sample/xg",
        query_string={
            "home_team": "Manchester United",
            "away_team": "Brighton & Hove Albion",
            "league": "PL",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["completeness"] == "season_plus_rolling"
    assert payload["refresh_status"] == "ready"
    assert payload["availability"] == "available"
    assert payload["fast_path"] is False
    assert payload["meta"]["league"] == "ENG-Premier League"
    assert "home_stats" in payload
    assert "away_stats" in payload

    home_recent = payload["home_stats"]["recent_matches"]
    away_recent = payload["away_stats"]["recent_matches"]
    assert len(home_recent) == 3
    assert len(away_recent) == 3

    home_rolling = payload["rolling_xg_home"]
    away_rolling = payload["rolling_xg_away"]

    assert home_rolling["window_len"] == 3
    assert away_rolling["window_len"] == 3
    assert len(home_rolling["for"]) == 3
    assert len(away_rolling["against"]) == 3
    assert home_rolling["dates"] == sorted(home_rolling["dates"], reverse=True)
    assert away_rolling["dates"] == sorted(away_rolling["dates"], reverse=True)

    assert xg_data_fetcher._PARTIAL_WINDOW_WARNINGS == {
        ("PL", "Manchester United", 5),
        ("PL", "Brighton & Hove Albion", 5),
    }


def test_match_context_fast_path_metadata(client, monkeypatch):
    season = xg_data_fetcher.get_xg_season()
    table = {
        "Manchester United": _sample_team_stats(1.8, 1.1),
        "Brighton & Hove Albion": _sample_team_stats(1.6, 1.2),
    }
    xg_data_fetcher._set_mem_cache('PL', season, table)

    monkeypatch.setattr(xg_data_fetcher, "_get_cached_team_logs_in_memory", lambda *args, **kwargs: [])
    monkeypatch.setattr(xg_data_fetcher, "_refresh_logs_async", lambda *args, **kwargs: "warming")

    response = client.get(
        "/match/sample/xg",
        query_string={
            "home_team": "Manchester United",
            "away_team": "Brighton & Hove Albion",
            "league": "PL",
        },
    )

    payload = response.get_json()
    assert payload["completeness"] == "season_only"
    assert payload["refresh_status"] == "warming"
    assert payload["availability"] == "available"
    assert payload["fast_path"] is True
    assert payload["meta"]["league"] == "ENG-Premier League"
    assert "home_stats" not in payload
    assert "away_stats" not in payload
    season_snapshot = payload.get("season")
    assert season_snapshot is not None
    assert "home_stats" in season_snapshot
    assert "away_stats" in season_snapshot
