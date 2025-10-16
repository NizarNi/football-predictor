import json
import sys
import types
from copy import deepcopy
from datetime import datetime

if "pandas" not in sys.modules:
    pandas_stub = types.ModuleType("pandas")
    pandas_stub.DataFrame = type("DataFrame", (), {})
    pandas_stub.Series = type("Series", (), {})

    def _isna(value):  # pragma: no cover - simple stub for tests without pandas
        return value is None

    pandas_stub.isna = _isna  # type: ignore[attr-defined]
    sys.modules["pandas"] = pandas_stub

if "soccerdata" not in sys.modules:
    soccerdata_stub = types.ModuleType("soccerdata")

    class _DummyFBref:  # pragma: no cover - placeholder stub
        def __init__(self, *args, **kwargs):
            pass

    soccerdata_stub.FBref = _DummyFBref  # type: ignore[attr-defined]
    sys.modules["soccerdata"] = soccerdata_stub

import pandas as pd
import pytest

from football_predictor import xg_data_fetcher

ALIAS_CASES = {
    "PL": [
        ("Wolves", "Wolverhampton Wanderers"),
        ("Nott'ham Forest", "Nottingham Forest"),
        ("Brighton", "Brighton & Hove Albion"),
    ],
    "PD": [
        ("Atletico Madrid", "Atlético Madrid"),
        ("Athletic Club", "Athletic Bilbao"),
        ("Alaves", "Deportivo Alavés"),
    ],
    "SA": [
        ("Inter Milan", "Inter"),
        ("Hellas Verona", "Hellas Verona"),
    ],
    "BL1": [
        ("Koln", "Köln"),
        ("Eint Frankfurt", "Eintracht Frankfurt"),
    ],
    "FL1": [
        ("Paris S-G", "Paris Saint-Germain"),
        ("Stade Brestois", "Brest"),
    ],
}


def _build_payloads():
    payloads = {}
    for league_code, pairs in ALIAS_CASES.items():
        league_payload = {}
        for idx, (legacy_key, _query_name) in enumerate(pairs, start=1):
            league_payload[legacy_key] = {
                "xg_for_per_game": round(1.0 + idx * 0.1, 2),
                "xg_against_per_game": round(0.7 + idx * 0.05, 2),
                "marker": f"{league_code}:{legacy_key}",
            }
        payloads[league_code] = league_payload
    return payloads


@pytest.fixture
def stub_league_cache(monkeypatch):
    payloads = _build_payloads()
    cache_store = {}

    def fake_load(cache_key):
        return cache_store.get(cache_key)

    def fake_save(cache_key, data):
        cache_store[cache_key] = (deepcopy(data), 0)

    def fake_fetch_and_cache(league_code, season, cache_key):
        data = deepcopy(payloads[league_code])
        fake_save(cache_key, data)
        return data

    monkeypatch.setattr(xg_data_fetcher, "load_from_cache", fake_load)
    monkeypatch.setattr(xg_data_fetcher, "save_to_cache", fake_save)
    monkeypatch.setattr(xg_data_fetcher, "_refresh_cache_in_background", lambda *args, **kwargs: None)
    monkeypatch.setattr(xg_data_fetcher, "_fetch_and_cache_league_xg_stats", fake_fetch_and_cache)

    return payloads


@pytest.mark.parametrize("league_code", sorted(ALIAS_CASES.keys()))
def test_alias_resolution_across_leagues(league_code, stub_league_cache):
    season = 2024
    # Warm cache
    xg_data_fetcher.fetch_league_xg_stats(league_code, season=season)

    for legacy_key, query_name in ALIAS_CASES[league_code]:
        canonical_stats = xg_data_fetcher.get_team_xg_stats(query_name, league_code, season=season)
        assert canonical_stats is not None
        assert canonical_stats["marker"] == f"{league_code}:{legacy_key}"

        alias_stats = xg_data_fetcher.get_team_xg_stats(legacy_key, league_code, season=season)
        assert alias_stats is not None
        assert alias_stats["marker"] == f"{league_code}:{legacy_key}"


def test_match_logs_timestamp_serialization(monkeypatch, tmp_path):
    cache_dir = tmp_path / "xg_cache"
    cache_dir.mkdir()

    monkeypatch.setattr(xg_data_fetcher, "CACHE_DIR", str(cache_dir))
    xg_data_fetcher.MATCH_LOGS_CACHE.clear()
    xg_data_fetcher._MATCH_LOGS_FETCH_LOCKS.clear()

    if not hasattr(pd, "Timestamp"):
        class FakeTimestamp:
            def __init__(self, value):
                if isinstance(value, datetime):
                    self._dt = value
                else:
                    self._dt = datetime.fromisoformat(str(value))

            def isoformat(self):
                return self._dt.isoformat()

        pd.Timestamp = FakeTimestamp  # type: ignore[attr-defined]

    timestamp_value = pd.Timestamp(datetime(2024, 5, 20, 12, 30))

    payload = [
        {
            "date": timestamp_value,
            "is_home": True,
            "opponent": "Arsenal",
            "gameweek": 1,
            "xg_for": 1.2,
            "xg_against": 0.8,
            "result": "W",
        }
    ]

    cache_path = xg_data_fetcher._team_match_logs_cache_path("PL", 2024, "Wolverhampton Wanderers")
    xg_data_fetcher._save_team_match_logs_to_disk("PL", 2024, "Wolverhampton Wanderers", payload)

    with open(cache_path, "r", encoding="utf-8") as fh:
        persisted = json.load(fh)

    assert isinstance(persisted[0]["date"], str)

    xg_data_fetcher.MATCH_LOGS_CACHE.clear()

    disk_loaded = xg_data_fetcher._load_team_match_logs_from_disk("PL", 2024, "Wolverhampton Wanderers")
    assert disk_loaded is not None
    assert isinstance(disk_loaded[0]["date"], str)

    calls = {"safe_called": False}

    def _unexpected_safe(*args, **kwargs):  # pragma: no cover - should not run
        calls["safe_called"] = True
        raise AssertionError("network fetch should not be required for disk hit")

    monkeypatch.setattr(xg_data_fetcher, "_safe_soccerdata_call", _unexpected_safe)

    second_result = xg_data_fetcher.fetch_team_match_logs(
        "Wolverhampton Wanderers", "PL", season=2024, request_memo_id=None
    )
    assert second_result
    assert isinstance(second_result[0]["date"], str)
    assert not calls["safe_called"]
