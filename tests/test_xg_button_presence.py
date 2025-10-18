from football_predictor.app import app


def test_xg_details_button_present_in_base_html():
    app.testing = True
    with app.test_client() as client:
        resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert "xG Details" in html
    assert 'id="xg-details-btn"' in html
    assert 'data-testid="xg-panel"' in html
