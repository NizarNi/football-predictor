import pytest


def test_aliases_map_to_supported_leagues():
    from football_predictor.xg_data_fetcher import LEAGUE_ALIASES, SUPPORTED_LEAGUES

    for alias, canonical in LEAGUE_ALIASES.items():
        assert canonical in SUPPORTED_LEAGUES, f"alias {alias} → {canonical} missing from SUPPORTED_LEAGUES"


def test_handle_league_xg_normalizes_and_returns_ready(monkeypatch):
    from football_predictor import xg_data_fetcher

    calls = []

    def fake_fetch(league_code, season=None, cache_only=False):
        calls.append((league_code, season, cache_only))
        return {"Juventus": {"xg_for_per_game": 1.6}}

    monkeypatch.setattr(xg_data_fetcher, "fetch_league_xg_stats", fake_fetch)
    monkeypatch.setattr(xg_data_fetcher, "_refresh_league_async", lambda *args, **kwargs: None)

    result = xg_data_fetcher.handle_league_xg("ITA", season="2025")

    assert calls == [("SA", 2025, True)]
    assert result.get("refresh_status") in {"ready", "warming", "debounced"}
    assert "unavailable" not in (result.get("availability") or "").lower()
