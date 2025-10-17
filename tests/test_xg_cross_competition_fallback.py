import pytest

pytest.importorskip("pandas")

from football_predictor.xg_data_fetcher import (  # noqa: E402
    SUPPORTED_DOMESTIC,
    fetch_league_xg_stats,
    get_match_xg_prediction,
)


@pytest.fixture(scope="module", autouse=True)
def warm_league_cache():
    for code in SUPPORTED_DOMESTIC:
        fetch_league_xg_stats(code)


@pytest.mark.parametrize(
    "home, away, competition",
    [
        ("Wolves", "Wolverhampton Wanderers", "FACUP"),
        ("Nott'ham Forest", "Nottingham Forest", "UCL"),
        ("Atlético Madrid", "Atlético Madrid", "COPA"),
        ("Athletic Club", "Athletic Bilbao", "UCL"),
        ("Inter Milan", "Inter", "COPPA"),
        ("Koln", "Köln", "DFB"),
        ("Paris S-G", "Paris Saint-Germain", "CDF"),
    ],
)
def test_cross_competition_infers_domestic_league(home, away, competition):
    payload = get_match_xg_prediction(home, away, competition)
    assert payload["available"] is True
    assert payload["home_xg"] > 0 or payload["away_xg"] > 0


def test_cross_competition_mismatch_returns_unavailable():
    payload = get_match_xg_prediction("PSG", "Inter", "UCL")
    assert payload["available"] is False
    assert "domestic-only" in payload.get("error", "")
    assert payload.get("availability") == "unavailable"
    assert payload.get("reason") == "Unsupported competition"
