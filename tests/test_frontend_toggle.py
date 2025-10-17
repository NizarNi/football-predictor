from football_predictor.app import app


def test_index_contains_xg_toggle_markup():
    app.testing = True
    with app.test_client() as client:
        response = client.get("/")
    html = response.get_data(as_text=True)
    assert "Show xG details" in html
    assert "xg-state-card" in html
    assert "Warming detailed logs… (cooldown active)" in html
