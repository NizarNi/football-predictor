from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta

import pytest

sys.modules.setdefault("pandas", types.ModuleType("pandas"))
sys.modules.setdefault("soccerdata", types.ModuleType("soccerdata"))

from football_predictor import app as app_module
from football_predictor import xg_data_fetcher
from football_predictor import request_memo as request_memo_module


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
def mock_btts_dependencies(monkeypatch):
    home_logs = [
        {
            "date": datetime(2024, 9, 14) - timedelta(days=7 * idx),
            "xg_for": 1.7 + idx * 0.05,
            "xg_against": 1.1 + idx * 0.04,
            "is_home": True,
            "opponent": f"Opponent {idx}",
            "result": "W",
        }
        for idx in range(4)
    ]
    away_logs = [
        {
            "date": datetime(2024, 9, 13) - timedelta(days=7 * idx),
            "xg_for": 1.3 + idx * 0.06,
            "xg_against": 1.4 + idx * 0.03,
            "is_home": False,
            "opponent": f"Rival {idx}",
            "result": "D" if idx % 2 else "L",
        }
        for idx in range(4)
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
            "Manchester United": _sample_team_stats(1.9, 1.2),
            "Brighton & Hove Albion": _sample_team_stats(1.5, 1.4),
        },
    )

    def fake_logs(league, season, team):
        if team == "Manchester United":
            return list(home_logs)
        if team == "Brighton & Hove Albion":
            return list(away_logs)
        return []

    monkeypatch.setattr(xg_data_fetcher, "_get_cached_team_logs_in_memory", fake_logs)
    monkeypatch.setattr(xg_data_fetcher, "_refresh_logs_async", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "football_predictor.name_resolver.resolve_team_name",
        lambda name, provider=None: name,
    )
    monkeypatch.setattr(app_module, "resolve_team_name", lambda name, provider=None: name)
    monkeypatch.setattr(request_memo_module, "resolve_team_name", lambda name, provider=None: name)

    monkeypatch.setattr(
        "football_predictor.understat_client.fetch_understat_standings",
        lambda league, season: [
            {"name": "Manchester United", "xGA": 30.0, "played": 20},
            {"name": "Brighton & Hove Albion", "xGA": 28.0, "played": 20},
        ],
    )
    monkeypatch.setattr("football_predictor.utils.get_current_season", lambda: 2024)
    monkeypatch.setattr(
        "football_predictor.odds_api_client.get_event_odds",
        lambda sport_key, event_id, regions=None, markets=None: {"odds": []},
    )
    monkeypatch.setattr(
        "football_predictor.odds_calculator.calculate_btts_from_odds",
        lambda odds: {"yes": {"probability": 0.55}, "no": {"probability": 0.45}},
    )
    monkeypatch.setattr(
        "football_predictor.odds_calculator.calculate_btts_probability_from_xg",
        lambda *args, **kwargs: 0.62,
    )


def test_btts_reuses_request_memo(monkeypatch, client):
    original_compute = xg_data_fetcher.compute_rolling_xg
    compute_calls: list[tuple[str, str]] = []

    def counting_compute(team_logs, N, league_only=True, **kwargs):
        compute_calls.append((kwargs.get("league"), kwargs.get("team")))
        return original_compute(team_logs, N, league_only=league_only, **kwargs)

    monkeypatch.setattr(xg_data_fetcher, "compute_rolling_xg", counting_compute)
    monkeypatch.setattr(request_memo_module, "compute_rolling_xg", counting_compute)

    response = client.get(
        "/match/sample_event/btts",
        query_string={
            "sport_key": "soccer_epl",
            "home_team": "Manchester United",
            "away_team": "Brighton & Hove Albion",
            "league": "PL",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert "rolling_xg_home" in payload
    assert "rolling_xg_away" in payload
    assert payload["rolling_xg_home"]["window_len"] == 4
    assert payload["rolling_xg_away"]["window_len"] == 4
    assert payload["xg_cache_source_home"] == "in_memory_cache"
    assert payload["xg_cache_source_away"] == "in_memory_cache"

    assert len(compute_calls) == 2
    leagues = {entry[0] for entry in compute_calls}
    teams = {entry[1] for entry in compute_calls}
    assert leagues == {"PL"}
    assert teams == {"Manchester United", "Brighton & Hove Albion"}
