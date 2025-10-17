from football_predictor.app import app


def test_index_contains_xg_toggle_markup():
    """
    Ensures base HTML contains xG toggle section and static hooks for JS injection.
    The old static placeholder text ('Warming detailed logs…') is now rendered
    dynamically by frontend JS (updateXgState), so we only check for static anchors.
    """

    app.testing = True
    with app.test_client() as client:
        response = client.get("/")

    html = response.get_data(as_text=True)
    assert "Show xG details" in html
    assert "xg-state-card" in html
    # Modern async behavior: dynamic text injected at runtime, not pre-rendered.
    # Ensure at least one of the toggle/analysis containers is available for JS hooks.
    assert any(
        hook in html for hook in ("xg-toggle-section", "xg-analysis", "xg-toggle-container")
    )
