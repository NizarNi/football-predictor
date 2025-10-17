from typing import List, Tuple

import pytest

pytest.importorskip("pandas")

from football_predictor import xg_data_fetcher


class ImmediateExecutor:
    def __init__(self):
        self.calls: List[Tuple] = []

    def submit(self, fn, *args, **kwargs):
        self.calls.append((fn, args, kwargs))
        result = fn(*args, **kwargs)

        class _ImmediateFuture:
            def result(self, timeout=None):
                return result

        return _ImmediateFuture()


@pytest.fixture(autouse=True)
def reset_caches():
    league_snapshot = dict(xg_data_fetcher._LEAGUE_MEM_CACHE)
    match_snapshot = dict(xg_data_fetcher.MATCH_LOGS_CACHE)
    background_snapshot = set(xg_data_fetcher._background_refreshes)
    debounce_snapshot = dict(xg_data_fetcher._DEBOUNCE)

    xg_data_fetcher._LEAGUE_MEM_CACHE.clear()
    xg_data_fetcher.MATCH_LOGS_CACHE.clear()
    xg_data_fetcher._background_refreshes.clear()
    xg_data_fetcher._DEBOUNCE.clear()
    yield
    xg_data_fetcher._LEAGUE_MEM_CACHE.clear()
    xg_data_fetcher._LEAGUE_MEM_CACHE.update(league_snapshot)
    xg_data_fetcher.MATCH_LOGS_CACHE.clear()
    xg_data_fetcher.MATCH_LOGS_CACHE.update(match_snapshot)
    xg_data_fetcher._background_refreshes.clear()
    xg_data_fetcher._background_refreshes.update(background_snapshot)
    xg_data_fetcher._DEBOUNCE.clear()
    xg_data_fetcher._DEBOUNCE.update(debounce_snapshot)


@pytest.fixture
def immediate_executor(monkeypatch):
    executor = ImmediateExecutor()
    monkeypatch.setattr(xg_data_fetcher, "_executor", executor)
    return executor


def _sample_team_stats(xg_for_per_game: float, xg_against_per_game: float):
    return {
        'xg_for_per_game': xg_for_per_game,
        'xg_against_per_game': xg_against_per_game,
        'scoring_clinicality': 0.1,
        'rolling_5': {},
        'form': None,
        'recent_matches': [],
        'using_rolling': False,
        'xg_for': xg_for_per_game * 10,
        'xg_against': xg_against_per_game * 10,
        'ps_xg_against': xg_against_per_game * 10,
        'matches_played': 10,
        'goals_for': xg_for_per_game * 10,
        'goals_against': xg_against_per_game * 10,
        'ps_xg_against_per_game': xg_against_per_game,
        'goals_for_per_game': xg_for_per_game,
        'goals_against_per_game': xg_against_per_game,
        'ps_xg_performance': 0,
    }


def test_fastpath_returns_cached_season_xg(monkeypatch, immediate_executor):
    season = xg_data_fetcher.get_xg_season()
    table = {
        'Arsenal': _sample_team_stats(1.8, 1.0),
        'Chelsea': _sample_team_stats(1.6, 1.2),
    }
    xg_data_fetcher._set_mem_cache('PL', season, table)

    refresh_calls = []

    def fake_ensure(league, team, season_arg=None):
        refresh_calls.append((league, team, season_arg))

    monkeypatch.setattr(xg_data_fetcher, "_ensure_team_logs_fresh", fake_ensure)

    result = xg_data_fetcher.get_match_xg_prediction(
        'Arsenal', 'Chelsea', 'PL', season=season
    )

    assert result['available'] is True
    assert result['fast_path'] is True
    assert result['completeness'] == 'season_only'
    assert result['refresh_status'] == 'warming'
    assert result['availability'] == 'available'
    assert 'home_xg' in result and 'away_xg' in result
    assert any(word in result.get('note', '').lower() for word in ['season xg', 'warming'])

    # two async warmers scheduled via executor wrapping function (_logs_task)
    assert len(refresh_calls) == 2
    ensure_targets = [fn for fn, *_ in immediate_executor.calls]
    assert all(call.__name__ == "_logs_task" for call in ensure_targets)


def test_cold_cache_returns_warming(monkeypatch, immediate_executor):
    season = xg_data_fetcher.get_xg_season()
    fetch_calls = []

    def fake_fetch(league, season_arg):
        fetch_calls.append((league, season_arg))
        table = {
            'Arsenal': _sample_team_stats(1.8, 1.0),
            'Chelsea': _sample_team_stats(1.6, 1.2),
        }
        xg_data_fetcher._set_mem_cache(league, season_arg, table)
        return table

    monkeypatch.setattr(xg_data_fetcher, "_fetch_and_cache_league_stats_now", fake_fetch)

    result = xg_data_fetcher.get_match_xg_prediction(
        'Arsenal', 'Chelsea', 'PL', season=season
    )

    assert result['available'] is False
    assert 'warming' in result['error'].lower()
    assert result['refresh_status'] == 'warming'
    assert result['availability'] == 'unavailable'
    # _refresh_league_async submits the fetch task to the (immediate) executor
    assert fetch_calls == [('PL', season)]


def test_cross_competition_fastpath(monkeypatch, immediate_executor):
    season = xg_data_fetcher.get_xg_season()
    table = {
        'Arsenal': _sample_team_stats(1.9, 0.9),
        'Chelsea': _sample_team_stats(1.5, 1.1),
    }
    xg_data_fetcher._set_mem_cache('PL', season, table)

    refresh_calls = []

    def fake_ensure(league, team, season_arg=None):
        refresh_calls.append((league, team, season_arg))

    monkeypatch.setattr(xg_data_fetcher, "_ensure_team_logs_fresh", fake_ensure)

    result = xg_data_fetcher.get_match_xg_prediction(
        'Arsenal', 'Chelsea', 'CL', season=season
    )

    expected_keys = {
        'available',
        'home_team',
        'away_team',
        'home_xg',
        'away_xg',
        'total_xg',
        'data_source_home',
        'data_source_away',
        'home_stats',
        'away_stats',
        'over_under_2_5',
        'result_prediction',
        'fast_path',
        'completeness',
        'refresh_status',
        'availability',
    }

    assert result['available'] is True
    assert result['fast_path'] is True
    assert result['completeness'] == 'season_only'
    assert result['refresh_status'] == 'warming'
    assert result['availability'] == 'available'
    assert expected_keys <= set(result.keys()) <= expected_keys | {'note'}
    assert len(refresh_calls) == 2
    assert refresh_calls == [('PL', 'Arsenal', season), ('PL', 'Chelsea', season)]
    assert result.get('note')


def test_league_mismatch_returns_guardrail(monkeypatch):
    season = xg_data_fetcher.get_xg_season()
    table = {
        'Arsenal': _sample_team_stats(1.9, 1.0),
    }
    xg_data_fetcher._set_mem_cache('PL', season, table)

    monkeypatch.setattr(xg_data_fetcher, "_get_cached_team_logs_in_memory", lambda *args, **kwargs: [])
    monkeypatch.setattr(xg_data_fetcher, "_refresh_logs_async", lambda *args, **kwargs: "debounced")

    result = xg_data_fetcher.get_match_xg_prediction(
        'Sunderland', 'Arsenal', 'PL', season=season
    )

    assert result['available'] is False
    assert result['availability'] == 'unavailable'
    assert result['reason'] == 'No per-match xG logs for this competition'
    assert result['refresh_status'] == 'ready'
