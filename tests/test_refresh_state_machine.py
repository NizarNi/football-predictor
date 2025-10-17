from typing import Any

from typing import Any

import pytest

from football_predictor import xg_data_fetcher


@pytest.fixture(autouse=True)
def reset_xg_caches():
    league_snapshot = dict(xg_data_fetcher._LEAGUE_MEM_CACHE)
    logs_snapshot = dict(xg_data_fetcher.MATCH_LOGS_CACHE)
    try:
        xg_data_fetcher._LEAGUE_MEM_CACHE.clear()
        xg_data_fetcher.MATCH_LOGS_CACHE.clear()
        yield
    finally:
        xg_data_fetcher._LEAGUE_MEM_CACHE.clear()
        xg_data_fetcher._LEAGUE_MEM_CACHE.update(league_snapshot)
        xg_data_fetcher.MATCH_LOGS_CACHE.clear()
        xg_data_fetcher.MATCH_LOGS_CACHE.update(logs_snapshot)


def _sample_stats(xg_for: float, xg_against: float) -> dict[str, Any]:
    return {
        "xg_for_per_game": xg_for,
        "xg_against_per_game": xg_against,
        "scoring_clinicality": 0.0,
        "rolling_5": {},
        "form": None,
        "recent_matches": [],
        "using_rolling": False,
        "xg_for": xg_for * 10,
        "xg_against": xg_against * 10,
        "ps_xg_against": xg_against * 10,
        "matches_played": 10,
        "goals_for": xg_for * 10,
        "goals_against": xg_against * 10,
        "ps_xg_against_per_game": xg_against,
        "goals_for_per_game": xg_for,
        "goals_against_per_game": xg_against,
        "ps_xg_performance": 0,
    }


def test_refresh_status_transitions(monkeypatch):
    season = xg_data_fetcher.get_xg_season()
    table = {
        "Arsenal": _sample_stats(1.8, 1.0),
        "Chelsea": _sample_stats(1.6, 1.2),
    }
    xg_data_fetcher._set_mem_cache("PL", season, table)

    state = {"phase": "debounced"}

    def fake_refresh(league_code, team, season_arg=None):
        return "debounced" if state["phase"] == "debounced" else "warming"

    def fake_cached(league_code, team, season_arg=None):
        if state["phase"] != "ready":
            return []
        return [
            {
                "match_id": 1,
                "xg_for": 1.2,
                "xg_against": 0.6,
                "date": "2024-01-01",
                "result": "W",
                "opponent": "Chelsea" if team == "Arsenal" else "Arsenal",
                "is_home": team == "Arsenal",
            }
        ]

    monkeypatch.setattr(xg_data_fetcher, "_refresh_logs_async", fake_refresh)
    monkeypatch.setattr(xg_data_fetcher, "_get_cached_team_logs_in_memory", fake_cached)

    first = xg_data_fetcher.get_match_xg_prediction("Arsenal", "Chelsea", "PL", season=season)
    assert first["refresh_status"] == "debounced"
    assert first["refresh_phase"] == "warming"
    assert first["fast_path"] is True

    state["phase"] = "warming"
    second = xg_data_fetcher.get_match_xg_prediction("Arsenal", "Chelsea", "PL", season=season)
    assert second["refresh_status"] == "warming"
    assert second["refresh_phase"] == "warming"
    assert second["fast_path"] is True

    state["phase"] = "ready"
    third = xg_data_fetcher.get_match_xg_prediction("Arsenal", "Chelsea", "PL", season=season)
    assert third["refresh_status"] == "ready"
    assert third["refresh_phase"] == "ready"
    assert third["fast_path"] is False
