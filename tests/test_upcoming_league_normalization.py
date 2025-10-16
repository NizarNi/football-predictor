import copy
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from typing import Callable

import sys
import types

sys.modules.setdefault("soccerdata", types.ModuleType("soccerdata"))
sys.modules.setdefault("pandas", types.ModuleType("pandas"))

import pytest
import requests
from unittest.mock import patch

from football_predictor import app as app_module
from football_predictor import config
from football_predictor.errors import APIError

@pytest.fixture(autouse=True)
def force_legacy_mode():
    original = config.USE_LEGACY_RESPONSES
    config.USE_LEGACY_RESPONSES = True
    try:
        yield
    finally:
        config.USE_LEGACY_RESPONSES = original


@pytest.fixture
def client():
    app = app_module.app
    app.testing = True
    return app.test_client()


def _prediction_stub():
    return {
        "prediction": "HOME_WIN",
        "confidence": 72,
        "probabilities": {
            "HOME_WIN": 0.55,
            "DRAW": 0.28,
            "AWAY_WIN": 0.17,
        },
        "bookmaker_count": 5,
        "best_odds": {"HOME_WIN": 1.9},
        "arbitrage": None,
    }


def _mock_prediction_dependencies(stack: ExitStack) -> None:
    stack.enter_context(
        patch(
            "football_predictor.app.calculate_predictions_from_odds",
            side_effect=lambda match: copy.deepcopy(_prediction_stub()),
        )
    )
    stack.enter_context(
        patch(
            "football_predictor.app.build_team_logo_urls",
            return_value=("home_logo.svg", "away_logo.svg"),
        )
    )
    stack.enter_context(
        patch("football_predictor.elo_client.get_team_elo", return_value=1500)
    )
    stack.enter_context(
        patch(
            "football_predictor.elo_client.calculate_elo_probabilities",
            return_value={"home_win": 0.6, "draw": 0.25, "away_win": 0.15},
        )
    )


@pytest.mark.parametrize("league_query", ["BL1", "Bundesliga", "bundesliga"])
def test_upcoming_league_normalization_returns_matches(client, league_query):
    sport_keys = []

    def fake_get_odds_for_sport(sport_key, regions="us,uk,eu", markets="h2h", odds_format="decimal"):
        sport_keys.append(sport_key)
        commence_time = (
            datetime.now(timezone.utc) + timedelta(hours=3)
        ).isoformat().replace("+00:00", "Z")
        return [
            {
                "id": "event-1",
                "commence_time": commence_time,
                "home_team": "Home FC",
                "away_team": "Away FC",
                "sport_key": sport_key,
                "sport_title": "Bundesliga",
                "bookmakers": [],
            }
        ]

    with ExitStack() as stack:
        _mock_prediction_dependencies(stack)
        stack.enter_context(
            patch(
                "football_predictor.odds_api_client.get_odds_for_sport",
                side_effect=fake_get_odds_for_sport,
            )
        )
        response = client.get(f"/upcoming?league={league_query}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["source"] == "The Odds API"
    assert payload["total_matches"] == 1
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["league_code"] == "BL1"
    assert sport_keys == ["soccer_germany_bundesliga"]


def test_upcoming_unknown_league_returns_warning(client):
    with patch(
        "football_predictor.app.get_upcoming_matches_with_odds",
        side_effect=AssertionError("get_upcoming_matches_with_odds should not be called"),
    ):
        response = client.get("/upcoming?league=UNKNOWN")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["matches"] == []
    assert payload["total_matches"] == 0
    assert payload["source"] == "odds_unavailable"
    assert payload["warning"] == "odds_unavailable_for_league"


@pytest.mark.parametrize(
    "exception_factory",
    [
        lambda: requests.Timeout("timeout"),
        lambda: APIError("OddsAPI", "TIMEOUT", "The Odds API did not respond in time."),
    ],
)
def test_upcoming_returns_warning_when_odds_fail(client, exception_factory: Callable[[], Exception]):
    exception = exception_factory()
    with patch(
        "football_predictor.app.get_upcoming_matches_with_odds",
        side_effect=exception,
    ):
        response = client.get("/upcoming?league=PL")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["matches"] == []
    assert payload["total_matches"] == 0
    assert payload["source"] == "odds_unavailable"
    assert payload["warning"] == "odds_unavailable_for_league"
