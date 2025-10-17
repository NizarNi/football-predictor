def test_index_contains_btts_and_xg_hooks():
    from football_predictor.app import app
    app.testing = True
    html = app.test_client().get("/").get_data(as_text=True)

    # Color resolver (reuses existing, thin wrapper present)
    assert "function resolveTeamColor(team)" in html
    # BTTS progress completion hook
    assert "function completeBttsProgress()" in html
    # xG toggle + analysis scaffolding
    assert 'id="xg-toggle-button"' in html
    assert 'id="xg-analysis"' in html
    # One-shot refresh + visibility helpers
    assert "function scheduleXgOneShotRefresh" in html
    assert "function ensureXgToggleVisible" in html
    assert "function toggleXgDetails" in html
