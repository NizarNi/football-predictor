import sys
import types
from unittest.mock import patch

import pytest

_fake_pandas = types.ModuleType("pandas")
_fake_pandas.isna = lambda value: False  # type: ignore[assignment]
sys.modules.setdefault("pandas", _fake_pandas)
sys.modules.setdefault("soccerdata", types.ModuleType("soccerdata"))

from football_predictor import app as app_module
from football_predictor import xg_data_fetcher


@pytest.fixture(autouse=True)
def clear_rolling_state():
    xg_data_fetcher._ROLLING_XG_MEMO.clear()
    xg_data_fetcher._PARTIAL_WINDOW_WARNINGS.clear()
    yield
    xg_data_fetcher._ROLLING_XG_MEMO.clear()
    xg_data_fetcher._PARTIAL_WINDOW_WARNINGS.clear()


@pytest.fixture
def client():
    app = app_module.app
    app.testing = True
    return app.test_client()


SAMPLE_LOGS = [
    {"date": "2024-04-20T12:00:00", "xg_for": 1.2, "xg_against": 0.6, "gameweek": 35},
    {"date": "2024-04-10T12:00:00", "xg_for": 0.9, "xg_against": 1.1, "gameweek": 34},
    {"date": "2024-03-30T12:00:00", "xg_for": 1.4, "xg_against": 0.8, "gameweek": 33},
    {"date": "2024-03-20T12:00:00", "xg_for": 1.1, "xg_against": 0.7, "gameweek": 32},
]


def _mock_league_stats():
    return {
        "Home FC": {
            "xg_for_per_game": 1.5,
            "xg_against_per_game": 1.0,
            "xg_for": 60,
            "xg_against": 40,
            "matches_played": 40,
        },
        "Away FC": {
            "xg_for_per_game": 1.4,
            "xg_against_per_game": 1.2,
            "xg_for": 56,
            "xg_against": 48,
            "matches_played": 40,
        },
    }


def test_btts_includes_rolling_xg_fields(client):
    with (
        patch("football_predictor.odds_api_client.get_event_odds", return_value={"bookmakers": []}),
        patch("football_predictor.odds_calculator.calculate_btts_from_odds", return_value={"yes": 0.55}),
        patch(
            "football_predictor.odds_calculator.calculate_btts_probability_from_xg",
            return_value={"yes_probability": 0.6, "no_probability": 0.4},
        ),
        patch("football_predictor.name_resolver.resolve_team_name", side_effect=lambda name, provider=None: name),
        patch("football_predictor.app.get_match_xg_prediction", return_value={"available": True}),
        patch("football_predictor.app.get_current_season", return_value=2024),
        patch(
            "football_predictor.xg_data_fetcher.fetch_team_match_logs",
            side_effect=lambda *args, **kwargs: list(SAMPLE_LOGS),
        ),
        patch("football_predictor.xg_data_fetcher.fetch_league_xg_stats", return_value=_mock_league_stats()),
        patch(
            "football_predictor.xg_data_fetcher.get_season_per_game_snapshot",
            side_effect=lambda team, league, season, league_stats=None: {
                "xg_for_per_game": 1.4,
                "xg_against_per_game": 1.1,
            },
        ),
    ):
        response = client.get(
            "/match/event123/btts?sport_key=soccer_epl&home_team=Home+FC&away_team=Away+FC&league=PL"
        )

    assert response.status_code == 200
    payload = response.get_json()
    payload = payload.get("data", payload)

    for key in ("rolling_xg_home", "rolling_xg_away"):
        assert key in payload
        snapshot = payload[key]
        assert set(snapshot.keys()) == {"xg_for_sum", "xg_against_sum", "window_len", "source"}
        assert 0 <= snapshot["window_len"] <= 4


def test_context_xg_arrays_and_rolling(client):
    unsorted_logs = [
        {"date": "2024-03-01T12:00:00", "xg_for": 0.9, "xg_against": 0.5, "gameweek": 30},
        {"date": "2024-03-20T12:00:00", "xg_for": 1.4, "xg_against": 0.8, "gameweek": 32},
        {"date": "2024-02-10T12:00:00", "xg_for": 1.0, "xg_against": 1.1, "gameweek": None},
    ]

    meta_payload = {
        "available": True,
        "meta": {
            "effective_league": "PL",
            "canonical_home": "Home FC",
            "canonical_away": "Away FC",
            "season": 2024,
        },
    }

    with (
        patch("football_predictor.app.get_match_xg_prediction", return_value=meta_payload),
        patch("football_predictor.name_resolver.resolve_team_name", side_effect=lambda name, provider=None: name),
        patch("football_predictor.xg_data_fetcher.fetch_league_xg_stats", return_value=_mock_league_stats()),
        patch(
            "football_predictor.xg_data_fetcher.fetch_team_match_logs",
            side_effect=lambda team, league, season: list(unsorted_logs),
        ),
        patch("football_predictor.app.get_current_season", return_value=2024),
        patch(
            "football_predictor.xg_data_fetcher.get_season_per_game_snapshot",
            side_effect=lambda team, league, season, league_stats=None: {
                "xg_for_per_game": 1.3,
                "xg_against_per_game": 1.1,
            },
        ),
    ):
        response = client.get(
            "/match/event999/xg?home_team=Home+FC&away_team=Away+FC&league=PL"
        )

    assert response.status_code == 200
    payload = response.get_json()
    payload = payload.get("data", payload)

    home_logs = payload["home_logs_filtered"]
    away_logs = payload["away_logs_filtered"]
    assert isinstance(home_logs, list)
    assert isinstance(away_logs, list)
    assert all(log.get("gameweek") for log in home_logs)
    assert all(log.get("gameweek") for log in away_logs)
    assert len(home_logs) == 2
    assert home_logs[0]["date"] > home_logs[1]["date"]

    for key in ("rolling_xg_home", "rolling_xg_away"):
        assert key in payload
        snapshot = payload[key]
        assert set(snapshot.keys()) == {"xg_for_sum", "xg_against_sum", "window_len", "source"}
        assert 0 <= snapshot["window_len"] <= 4


def test_partial_window_warns_once():
    logs = [
        {"date": "2024-04-01T12:00:00", "xg_for": 1.0, "xg_against": 0.7, "gameweek": 30},
        {"date": "2024-03-25T12:00:00", "xg_for": 1.1, "xg_against": 0.9, "gameweek": 29},
    ]

    xg_data_fetcher._ROLLING_XG_MEMO.clear()
    xg_data_fetcher._PARTIAL_WINDOW_WARNINGS.clear()

    xg_data_fetcher.compute_rolling_xg(
        logs,
        N=4,
        league_only=True,
        team_identifier="Home FC",
        league="PL",
        season=2024,
    )

    assert ("Home FC", "PL", 2024) in xg_data_fetcher._PARTIAL_WINDOW_WARNINGS
    snapshot = set(xg_data_fetcher._PARTIAL_WINDOW_WARNINGS)

    xg_data_fetcher._ROLLING_XG_MEMO.clear()

    xg_data_fetcher.compute_rolling_xg(
        logs,
        N=4,
        league_only=True,
        team_identifier="Home FC",
        league="PL",
        season=2024,
    )

    assert xg_data_fetcher._PARTIAL_WINDOW_WARNINGS == snapshot
