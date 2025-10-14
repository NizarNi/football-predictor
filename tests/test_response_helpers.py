import pytest
from football_predictor.app import app


@pytest.fixture
def client():
    app.testing = True
    with app.test_client() as client:
        yield client


def test_status_endpoint_returns_wrapped(client):
    """Modern endpoint: should return wrapped JSON with status/message/data"""
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data.keys()) == {"status", "message", "data"}
    assert data["status"] == "ok"
    assert "legacy_mode" in data["data"]


@pytest.mark.parametrize("endpoint", ["/upcoming", "/search", "/career_xg"])
def test_legacy_endpoints_unwrapped(client, endpoint):
    """Legacy endpoints should return unwrapped JSON (no 'status' key)"""
    if endpoint == "/search":
        resp = client.post(endpoint, data={"team_name": "Barcelona"})
    elif endpoint == "/career_xg":
        resp = client.get(endpoint + "?team=Barcelona&league=la_liga")
    else:
        resp = client.get(endpoint)

    data = resp.get_json()
    assert isinstance(data, dict)
    assert "status" not in data  # legacy format
    assert "error" in data or "matches" in data or "career_xg" in data


def test_predict_endpoint_wrapped(client):
    """Modern endpoint should return wrapped JSON."""
    resp = client.get("/predict/test123")
    data = resp.get_json()
    assert "status" in data
    assert "data" in data
    assert "predictions" in data["data"]

