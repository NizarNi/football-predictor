from pathlib import Path

import pytest


def test_unavailable_league_returns_ready(monkeypatch):
    from football_predictor import xg_data_fetcher

    monkeypatch.setattr(
        xg_data_fetcher,
        "_resolve_fbref_team_name",
        lambda name, context: name,
    )
    monkeypatch.setattr(
        xg_data_fetcher,
        "_pick_effective_league",
        lambda league, home, away: ("MLS", None),
    )
    monkeypatch.setattr(
        xg_data_fetcher,
        "fetch_league_xg_stats",
        lambda *args, **kwargs: {},
    )

    result = xg_data_fetcher.get_match_xg_prediction("Team A", "Team B", "MLS")
    assert result["refresh_status"] == "ready"
    assert result["availability"] == "unavailable"
    assert result.get("message", "").startswith("xG data unavailable")


def _load_template() -> str:
    return Path("football_predictor/templates/index.html").read_text(encoding="utf-8")


def test_btts_progress_completion_hook_present():
    template = _load_template()
    assert "function completeBttsProgress" in template
    assert "completeBttsProgress();" in template


@pytest.mark.parametrize("team_name", ["Chelsea", "Unknown Club"])
def test_team_color_helper_palette(team_name):
    template = _load_template()
    assert "function getTeamColor" in template
    assert "#0d6efd" in template
    if team_name == "Chelsea":
        assert "\"Chelsea\": \"#034694\"" in template
    else:
        # default color should be present in template
        assert '"_default":"#0d6efd"' in template.replace(" ", "")


