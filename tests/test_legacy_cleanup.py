import pytest
from football_predictor.app import app


@pytest.fixture
def client():
    app.testing = True
    with app.test_client() as client:
        yield client


def test_match_endpoint_returns_410(client):
    resp = client.get("/match/12345")
    assert resp.status_code == 410
    data = resp.get_json()
    assert data.get("ok") is False
    assert data.get("error") == "Endpoint deprecated"


def test_predict_endpoint_returns_410(client):
    resp = client.get("/predict/abcdef")
    assert resp.status_code == 410
    data = resp.get_json()
    assert data.get("ok") is False
    assert data.get("error") == "Endpoint deprecated"


def test_process_data_returns_410(client):
    resp = client.post("/process_data")
    assert resp.status_code == 410
    data = resp.get_json()
    assert data.get("ok") is False
    assert data.get("error") == "Endpoint deprecated"
