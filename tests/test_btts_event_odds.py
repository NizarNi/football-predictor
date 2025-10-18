import requests


def test_btts_404_soft_fail(monkeypatch):
    from football_predictor import odds_api_client as oc

    monkeypatch.setattr(oc, "API_KEYS", ["test-key"])
    monkeypatch.setattr(oc, "invalid_keys", set())

    def fake_request_with_retries(*args, **kwargs):
        response = requests.Response()
        response.status_code = 404
        response._content = b""
        response.url = "https://example.test"
        raise requests.exceptions.HTTPError(response=response)

    monkeypatch.setattr(oc, "request_with_retries", fake_request_with_retries)

    payload = oc.get_event_odds("soccer_epl", "evt-123", markets="btts")
    assert payload == {"bookmakers": []}
