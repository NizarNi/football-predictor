from typing import Dict

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
                    "meta": {"location": "home"},
                    "scores": {"total": 2},
                },
                {
                    "participant": {"id": 2, "name": "Away"},
                    "meta": {"location": "away"},
                    "scores": {"total": 1},
                },
            ]
        },
        "scores": [],
        "state": {"short_name": "NS"},
    }

    def fake_fetch(league_id: int, start: str, end: str):
        return [fixture_payload], 321, False

    monkeypatch.setattr(sportmonks, "fetch_league_window", fake_fetch)

    adapter = sportmonks.SportmonksAdapter()
    fixtures = adapter.get_fixtures("EPL", "2024-03-01T00:00:00Z", "2024-03-02T00:00:00Z")

    assert len(fixtures) == 1
    item = fixtures[0]
    assert item["match_id"] == "555"
    assert item["home"]["name"] == "Home"
    assert item["away"]["name"] == "Away"
