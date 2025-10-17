def test_xg_available_sets_ready(monkeypatch):
    from football_predictor import xg_data_fetcher

    dummy = {"xg_stats": {"team": "Chelsea", "xg": 1.3}}

    def fake_fetch(*args, **kwargs):
        return dummy

    monkeypatch.setattr(xg_data_fetcher, "fetch_league_xg_stats", fake_fetch)
    monkeypatch.setattr(xg_data_fetcher, "_refresh_league_async", lambda *args, **kwargs: None)

    result = xg_data_fetcher.handle_league_xg("PL", season="2025")

    assert result["availability"] == "ready"


def test_unavailable_league_remains_unavailable():
    from football_predictor import xg_data_fetcher

    result = xg_data_fetcher.handle_league_xg("XYZ", season="2025")

    assert result["availability"] == "unavailable"
