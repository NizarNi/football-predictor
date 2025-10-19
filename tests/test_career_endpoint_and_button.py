import sys
import types

import pytest

if "soccerdata" not in sys.modules:
    soccerdata_stub = types.ModuleType("soccerdata")

    class _StubFBref:  # pragma: no cover - should never be instantiated in these tests
        def __init__(self, *args, **kwargs):
            raise RuntimeError("FBref client should not be constructed in tests")

    soccerdata_stub.FBref = _StubFBref  # type: ignore[attr-defined]
    sys.modules["soccerdata"] = soccerdata_stub

from football_predictor.app import app


@pytest.fixture()
def client(monkeypatch):
    def _fake_fetch(team, league):
        return {
            "career_xg_per_game": 1.11,
            "career_xga_per_game": 0.9,
            "seasons_count": 5,
        }

    monkeypatch.setattr(
        "football_predictor.xg_data_fetcher.fetch_career_xg_stats",
        _fake_fetch,
    )

    app.testing = True
    with app.test_client() as client:
        yield client


def test_career_endpoint_shape(client):
    resp = client.get("/career_xg?team=Arsenal&league=PL")
    assert resp.status_code == 200
    data = resp.get_json()

    career = data.get("career_xg", data)
    assert isinstance(career, dict)
    assert career["career_xg_per_game"] == 1.11
    assert career["career_xga_per_game"] == 0.9
    assert career["seasons_count"] == 5


def test_career_button_present_on_page(client):
    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert "Show Career Stats (2021-2025)" in html
    assert 'id="btn-home-career"' in html
    assert 'id="btn-away-career"' in html
