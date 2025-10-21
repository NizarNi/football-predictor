from typing import Any, Dict

import pytest

from football_predictor.adapters import sportmonks


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sportmonks, "_cache", sportmonks._TTL())


@pytest.fixture(autouse=True)
def _force_league(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sportmonks, "sportmonks_league_id", lambda code: 999)
    monkeypatch.setattr(sportmonks, "SPORTMONKS_KEY", "token")


def test_get_fixtures_handles_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(league_id: int, start: str, end: str):
        return [], None, False

    monkeypatch.setattr(sportmonks, "fetch_league_window", fake_fetch)

    adapter = sportmonks.SportmonksAdapter()
    fixtures = adapter.get_fixtures("EPL", "2024-03-01T00:00:00Z", "2024-03-02T00:00:00Z")

    assert fixtures == []


def test_get_fixtures_maps_basic_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_payload: Dict[str, Any] = {
        "id": 555,
        "starting_at": "2024-03-01T15:00:00+00:00",
        "participants": {
            "data": [
                {
                    "participant": {"id": 1, "name": "Home"},
                    "team": {"data": {"id": 1, "name": "Home", "image_path": "https://cdn/home.png"}},
                    "meta": {"location": "home"},
                    "scores": {"total": 2},
                },
                {
                    "participant": {"id": 2, "name": "Away"},
                    "team": {"data": {"id": 2, "name": "Away", "image_path": "https://cdn/away.png"}},
                    "meta": {"location": "away"},
                    "scores": {"total": 1},
                },
            ]
        },
        "scores": [],
        "state": {"short_name": "NS"},
        "round": {"data": {"name": "Matchday 26"}},
        "venue": {"data": {"name": "Anfield", "city": "Liverpool"}},
        "tvstations": {"data": [{"name": "Sky Sports"}]},
        "referee": {"data": {"fullname": "John Doe"}},
    }

    def fake_fetch(league_id: int, start: str, end: str):
        return [fixture_payload], 321, False

    monkeypatch.setattr(sportmonks, "fetch_league_window", fake_fetch)

    adapter = sportmonks.SportmonksAdapter()
    fixtures = adapter.get_fixtures("EPL", "2024-03-01T00:00:00Z", "2024-03-02T00:00:00Z")

    assert len(fixtures) == 1
    item = fixtures[0]
    assert item["match_id"] == "555"
    assert item["fixture_id"] == 555
    assert item["kickoff_iso"] == "2024-03-01T15:00:00Z"
    assert item["kickoff_utc"] == "2024-03-01T15:00:00Z"
    assert item["league_id"] == 999
    assert item["season_id"] == 321
    assert item["round"] == "Matchday 26"
    assert item["venue"] == {"name": "Anfield", "city": "Liverpool"}
    assert item["home"]["name"] == "Home"
    assert item["away"]["name"] == "Away"
    assert item["home"]["logo"] == "https://cdn/home.png"
    assert item["away"]["logo"] == "https://cdn/away.png"
    assert item["tv_stations"] == ["Sky Sports"]
    assert item["referee"] == "John Doe"


def test_get_fixtures_can_skip_logos(monkeypatch: pytest.MonkeyPatch) -> None:
    payload: Dict[str, Any] = {
        "id": 1,
        "starting_at": "2024-03-01T15:00:00+00:00",
        "participants": {
            "data": [
                {
                    "participant": {"id": 10, "name": "One"},
                    "team": {"data": {"id": 10, "name": "One", "image_path": "https://cdn/one.png"}},
                    "meta": {"location": "home"},
                },
                {
                    "participant": {"id": 20, "name": "Two"},
                    "team": {"data": {"id": 20, "name": "Two", "image_path": "https://cdn/two.png"}},
                    "meta": {"location": "away"},
                },
            ]
        },
        "scores": [],
        "state": {"short_name": "NS"},
    }

    def fake_fetch(league_id: int, start: str, end: str):
        return [payload], 123, False

    monkeypatch.setattr(sportmonks, "fetch_league_window", fake_fetch)

    adapter = sportmonks.SportmonksAdapter()
    fixtures = adapter.get_fixtures(
        "EPL",
        "2024-03-01T00:00:00Z",
        "2024-03-02T00:00:00Z",
        include_logos=False,
    )

    assert fixtures[0]["home"]["logo"] is None
    assert fixtures[0]["away"]["logo"] is None
