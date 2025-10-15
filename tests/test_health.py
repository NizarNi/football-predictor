import pytest

from football_predictor.app import app


@pytest.fixture
def client():
    app.testing = True
    with app.test_client() as client:
        yield client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["message"] == "OK"
    data = payload["data"]
    assert data["ok"] is True
    assert "ts" in data
