from football_predictor.app import app


def test_xg_contract_includes_refresh_status_field():
    """
    The xG details flow relies on refresh_status to decide ready/warming.
    This test merely asserts the field exists in a happy-path call using known query params.
    """
    app.testing = True
    with app.test_client() as client:
        # Use minimal params; the route is tolerant in existing tests
        # We don't assert values here to avoid coupling; just the field's presence.
        response = client.get("/match/dummy-event/xg?sport_key=&home_team=Home&away_team=Away&league=PL")
    body = response.get_data(as_text=True)
    assert "refresh_status" in body
