import pytest

from football_predictor.adapters import sportmonks_seasons as seasons


@pytest.fixture(autouse=True)
def _ensure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPORTMONKS_KEY", "test-key")
    # refresh TOKEN used by module if needed
    monkeypatch.setattr(seasons, "TOKEN", "test-key", raising=False)


def test_get_current_prefers_league(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_sm_get(path: str, params=None):
        calls.append(path)
        assert path == "/leagues/8"
        return {"data": {"currentSeason": {"id": 101}}}

    resolver = seasons.SeasonResolver(ttl_sec=60)
    monkeypatch.setattr(seasons, "_sm_get", fake_sm_get)

    assert resolver.get_current(8) == 101
    assert calls == ["/leagues/8"]


def test_get_current_falls_back_to_seasons(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_sm_get(path: str, params=None):
        calls.append(path)
        if path.startswith("/leagues"):
            return {"data": {}}
        return {"data": [{"id": 202, "is_current": True}]}

    resolver = seasons.SeasonResolver(ttl_sec=60)
    monkeypatch.setattr(seasons, "_sm_get", fake_sm_get)

    assert resolver.get_current(8) == 202
    assert calls == ["/leagues/8", "/seasons"]


def test_cache_hit_avoids_second_call(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = {"count": 0}

    def fake_sm_get(path: str, params=None):
        call_count["count"] += 1
        return {"data": {"currentSeason": {"id": 303}}}

    resolver = seasons.SeasonResolver(ttl_sec=60)
    monkeypatch.setattr(seasons, "_sm_get", fake_sm_get)

    assert resolver.get_current(8) == 303
    assert resolver.get_current(8) == 303
    assert call_count["count"] == 1


def test_get_for_date_matches_range(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_sm_get(path: str, params=None):
        return {
            "data": [
                {
                    "id": 404,
                    "starting_at": "2024-07-01",
                    "ending_at": "2025-06-30",
                }
            ]
        }

    resolver = seasons.SeasonResolver(ttl_sec=60)
    monkeypatch.setattr(seasons, "_sm_get", fake_sm_get)

    assert resolver.get_for_date(10, "2024-10-01") == 404
