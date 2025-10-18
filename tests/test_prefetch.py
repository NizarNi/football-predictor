import sys
import time
import types


def test_warm_top5_leagues_concurrent(monkeypatch):
    calls = []

    def fake_warm(league_code):
        calls.append(league_code)
        time.sleep(0.05)
        return True

    monkeypatch.setitem(sys.modules, 'soccerdata', types.ModuleType('soccerdata'))
    from football_predictor.xg_data_fetcher import warm_top5_leagues

    start = time.monotonic()
    results = warm_top5_leagues(warm_fn=fake_warm)
    duration = time.monotonic() - start

    assert duration < 10
    expected_calls = {"PL", "BL1", "SA", "PD", "FL1", "CL", "EL"}
    assert set(calls) == expected_calls
    # Results are keyed by the external codes used for dispatch
    expected_result_keys = {"ENG", "GER", "ITA", "ESP", "FRA", "CL", "EL"}
    assert set(results.keys()) == expected_result_keys
    assert all(results.get(code) for code in results)
