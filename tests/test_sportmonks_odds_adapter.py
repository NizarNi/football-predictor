from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from football_predictor.adapters import sportmonks_odds


@pytest.fixture(autouse=True)
def _reset_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sportmonks_odds, "_fixture_cache", sportmonks_odds._TTLCache())
    monkeypatch.setattr(sportmonks_odds, "_bookmaker_cache", sportmonks_odds._TTLCache())
    monkeypatch.setattr(sportmonks_odds, "SPORTMONKS_KEY", "token")
    monkeypatch.setattr(sportmonks_odds, "sportmonks_league_id", lambda code: 999)


def _make_fixture(odds: Any, **extra: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": 123,
        "season_id": 2024,
        "starting_at": "2024-03-10T20:00:00+00:00",
        "state": {"short_name": "NS"},
        "participants": {
            "data": [
                {
                    "participant": {
                        "id": 1,
                        "name": "Home FC",
                        "image_path": "https://img/home.png",
                    },
                    "meta": {"location": "home"},
                },
                {
                    "participant": {
                        "id": 2,
                        "name": "Away FC",
                        "image_path": "https://img/away.png",
                    },
                    "meta": {"location": "away"},
                },
            ]
        },
        "venue": {"data": {"id": 55, "name": "Arena", "city": "City"}},
        "round": {"data": {"name": "Round 28"}},
        "odds": odds,
    }
    payload.update(extra)
    return payload


def test_odds_merge_best_avg(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2024, 3, 9, 20, 0, tzinfo=timezone.utc)
    adapter = sportmonks_odds.SportmonksOddsAdapter(now_fn=lambda: now)

    fixture_payload = _make_fixture(
        odds=[
            {
                "bookmaker_id": 10,
                "bookmaker": {"data": {"id": 10, "name": "Bookie A"}},
                "market": {"data": {"key": "winning"}},
                "last_update": "2024-03-09T18:00:00+00:00",
                "values": [
                    {"label": "1", "value": "1.90"},
                    {"label": "X", "value": "3.60"},
                    {"label": "2", "value": "4.80"},
                ],
            },
            {
                "bookmaker_id": 20,
                "bookmaker": {"data": {"id": 20, "name": "Bookie B"}},
                "market": {"data": {"key": "winning"}},
                "updated_at": "2024-03-09T19:00:00+00:00",
                "odds": [
                    {"label": "Home", "odd": 1.95},
                    {"label": "Draw", "odd": 3.55},
                    {"label": "Away", "odd": 4.70},
                ],
            },
        ]
    )

    monkeypatch.setattr(
        adapter,
        "_fetch_fixtures_between",
        lambda league_id, start, end: [fixture_payload],
    )

    fixtures = adapter.get_fixtures("EPL", "2024-03-01T00:00:00Z", "2024-04-01T00:00:00Z")
    assert len(fixtures) == 1
    item = fixtures[0]

    assert item["odds_status"] == "available"
    best = item["odds"]["best"]
    avg = item["odds"]["avg"]
    assert best == {"home": 1.95, "draw": 3.6, "away": 4.8}
    assert avg == {"home": 1.925, "draw": 3.575, "away": 4.75}
    assert len(item["odds"]["bookmakers"]) == 2


def test_missing_logo_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2024, 3, 1, tzinfo=timezone.utc)
    adapter = sportmonks_odds.SportmonksOddsAdapter(now_fn=lambda: now)

    fixture_payload = _make_fixture(
        odds=[],
        participants={
            "data": [
                {"participant": {"id": 1, "name": "Home"}, "meta": {"location": "home"}},
                {"participant": {"id": 2, "name": "Away"}, "meta": {"location": "away"}},
            ]
        },
    )

    monkeypatch.setattr(
        adapter,
        "_fetch_fixtures_between",
        lambda league_id, start, end: [fixture_payload],
    )

    fixtures = adapter.get_fixtures("EPL", "2024-03-01T00:00:00Z", "2024-03-20T00:00:00Z")
    item = fixtures[0]
    assert item["home_team"]["logo"] == sportmonks_odds.DEFAULT_LOGO_PATH
    assert item["away_team"]["logo"] == sportmonks_odds.DEFAULT_LOGO_PATH
    assert item["odds"] is None
    assert item["odds_status"] == "unavailable"


def test_bookmaker_directory_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2024, 3, 5, tzinfo=timezone.utc)
    adapter = sportmonks_odds.SportmonksOddsAdapter(now_fn=lambda: now)

    sportmonks_odds._bookmaker_cache.set((77,), "Directory BK")

    fixture_payload = _make_fixture(
        odds=[
            {
                "bookmaker_id": 77,
                "market": {"data": {"key": "winning"}},
                "last_update": "2024-03-05T00:00:00+00:00",
                "values": [
                    {"label": "1", "value": "2.10"},
                    {"label": "X", "value": "3.20"},
                    {"label": "2", "value": "3.90"},
                ],
            }
        ]
    )

    def fail_load() -> Dict[int, str]:
        raise AssertionError("should not load directory")

    monkeypatch.setattr(adapter, "_load_bookmakers", fail_load)
    monkeypatch.setattr(
        adapter,
        "_fetch_fixtures_between",
        lambda league_id, start, end: [fixture_payload],
    )

    fixtures = adapter.get_fixtures("EPL", "2024-03-01T00:00:00Z", "2024-03-20T00:00:00Z")
    item = fixtures[0]
    bookmaker = item["odds"]["bookmakers"][0]
    assert bookmaker["bookmaker_name"] == "Directory BK"
    assert item["odds_status"] == "available"


def test_stale_odds_filtered(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2024, 3, 10, tzinfo=timezone.utc)
    adapter = sportmonks_odds.SportmonksOddsAdapter(now_fn=lambda: now)

    stale_fixture = _make_fixture(
        odds=[
            {
                "bookmaker_id": 5,
                "bookmaker": {"data": {"id": 5, "name": "Old Bookie"}},
                "market": {"data": {"key": "winning"}},
                "last_update": "2024-03-07T00:00:00+00:00",
                "values": [
                    {"label": "1", "value": "1.50"},
                    {"label": "X", "value": "4.00"},
                    {"label": "2", "value": "6.00"},
                ],
            }
        ]
    )

    monkeypatch.setattr(
        adapter,
        "_fetch_fixtures_between",
        lambda league_id, start, end: [stale_fixture],
    )

    fixtures = adapter.get_fixtures("EPL", "2024-03-01T00:00:00Z", "2024-03-20T00:00:00Z")
    item = fixtures[0]
    assert item["odds"] is None
    assert item["odds_status"] == "unavailable"
