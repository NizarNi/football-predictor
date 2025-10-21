from __future__ import annotations

from typing import Any, Dict

import pytest

from flask import Flask

from football_predictor.routes import sportmonks_api


class DummyFeedService:
    def __init__(self, payload: Dict[str, Any]):
        self.payload = payload
        self.last_kwargs: Dict[str, Any] | None = None

    def load_page(self, **kwargs: Any) -> Dict[str, Any]:
        self.last_kwargs = kwargs
        return self.payload


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sportmonks_api, "_service_singleton", None)
    test_app = Flask(__name__)
    test_app.register_blueprint(sportmonks_api.bp)
    with test_app.test_client() as test_client:
        yield test_client


def test_feed_formats_items_with_logos(monkeypatch: pytest.MonkeyPatch, client) -> None:
    raw_item = {
        "match_id": "10",
        "fixture_id": 10,
        "kickoff_iso": "2024-03-01T15:00:00Z",
        "kickoff_utc": "2024-03-01T15:00:00Z",
        "status": "NS",
        "league_id": 8,
        "season_id": 12345,
        "round": "Matchday 1",
        "venue": {"name": "Anfield", "city": "Liverpool"},
        "home": {"id": 1, "name": "Liverpool", "logo": "https://cdn/home.png"},
        "away": {"id": 2, "name": "Chelsea", "logo": "https://cdn/away.png"},
        "tv_stations": ["Sky Sports"],
        "referee": "John Doe",
    }
    service = DummyFeedService(
        {
            "items": [raw_item],
            "next_cursor": None,
            "prev_cursor": None,
            "has_more_future": False,
            "has_more_past": False,
        }
    )
    monkeypatch.setattr(sportmonks_api, "_service_singleton", service)

    resp = client.get("/api/smonks/feed?leagues=EPL")
    data = resp.get_json()

    assert resp.status_code == 200
    assert service.last_kwargs is not None
    assert service.last_kwargs["include_logos"] is True
    item = data["items"][0]
    assert item["fixture_id"] == 10
    assert item["home_team"]["logo"] == "https://cdn/home.png"
    assert item["venue"] == {"name": "Anfield", "city": "Liverpool"}
    assert item["tv_stations"] == ["Sky Sports"]
    assert item["referee"] == "John Doe"


def test_feed_can_disable_logos(monkeypatch: pytest.MonkeyPatch, client) -> None:
    raw_item = {
        "match_id": "20",
        "fixture_id": 20,
        "kickoff_iso": "2024-03-02T18:00:00Z",
        "status": "NS",
        "league_id": 82,
        "season_id": 54321,
        "home": {"id": 4, "name": "Bayern", "logo": "https://cdn/bayern.png"},
        "away": {"id": 5, "name": "Dortmund", "logo": "https://cdn/bvb.png"},
        "venue": {},
    }
    service = DummyFeedService(
        {
            "items": [raw_item],
            "next_cursor": "cursor",
            "prev_cursor": None,
            "has_more_future": True,
            "has_more_past": False,
        }
    )
    monkeypatch.setattr(sportmonks_api, "_service_singleton", service)

    resp = client.get("/api/smonks/feed?include_logos=false&leagues=EPL")
    data = resp.get_json()

    assert resp.status_code == 200
    assert service.last_kwargs is not None
    assert service.last_kwargs["include_logos"] is False
    item = data["items"][0]
    assert item["home_team"]["logo"] is None
    assert item["away_team"]["logo"] is None
