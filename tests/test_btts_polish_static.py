from football_predictor.app import app


def test_btts_progress_and_color_hooks_present():
    app.testing = True
    with app.test_client() as client:
        html = client.get("/").get_data(as_text=True)

    assert "btts-progress" in html
    assert "function completeBttsProgress()" in html
    assert "buildSeasonSnapshotHtml" in html
    assert "getTeamBrandColor(" in html
    assert 'style="color:' in html or "style='color:" in html
