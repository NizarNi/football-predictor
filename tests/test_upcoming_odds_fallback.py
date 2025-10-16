import copy
import sys
import types
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import requests

sys.modules.setdefault("soccerdata", types.ModuleType("soccerdata"))
sys.modules.setdefault("pandas", types.ModuleType("pandas"))

from football_predictor import app as app_module
from football_predictor import config
from football_predictor.errors import APIError


class TestUpcomingOddsFallback(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        self.app.testing = True
        self.client = self.app.test_client()
        self._original_flag = config.USE_LEGACY_RESPONSES
        config.USE_LEGACY_RESPONSES = True

    def tearDown(self):
        config.USE_LEGACY_RESPONSES = self._original_flag

    def _mock_prediction_dependencies(self):
        predictions = {
            "prediction": "HOME_WIN",
            "confidence": 70,
            "probabilities": {
                "HOME_WIN": 0.5,
                "DRAW": 0.3,
                "AWAY_WIN": 0.2,
            },
            "bookmaker_count": 3,
            "best_odds": {"HOME_WIN": 1.9},
            "arbitrage": None,
        }

        stack = ExitStack()
        stack.enter_context(
            patch(
                "football_predictor.app.calculate_predictions_from_odds",
                return_value=copy.deepcopy(predictions),
            )
        )
        stack.enter_context(
            patch(
                "football_predictor.app.build_team_logo_urls",
                return_value=("home_logo", "away_logo"),
            )
        )
        stack.enter_context(
            patch("football_predictor.elo_client.get_team_elo", return_value=1500)
        )
        stack.enter_context(
            patch(
                "football_predictor.elo_client.calculate_elo_probabilities",
                return_value={"home_win": 0.55, "draw": 0.25, "away_win": 0.2},
            )
        )
        return stack

    def test_upcoming_timeout_returns_warning_payload(self):
        with patch(
            "football_predictor.app.get_upcoming_matches_with_odds",
            side_effect=requests.Timeout,
        ):
            response = self.client.get("/upcoming?league=PL")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["matches"], [])
        self.assertEqual(payload["source"], "odds_unavailable")
        self.assertEqual(payload["warning"], "odds_unavailable_for_league")

    def test_upcoming_normalizes_bundesliga_league(self):
        sample_match = {
            "commence_time": "2024-01-01T12:00:00Z",
            "home_team": "Team A",
            "away_team": "Team B",
            "id": "match-1",
            "event_id": "event-1",
            "sport_key": "soccer_germany_bundesliga",
            "league": "Bundesliga",
            "league_code": "BL1",
            "bookmakers": [],
        }

        captured = {}

        def fake_get(league_codes=None, next_n_days=None):
            captured["league_codes"] = list(league_codes or [])
            return [copy.deepcopy(sample_match)]

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "football_predictor.app.get_upcoming_matches_with_odds",
                    side_effect=fake_get,
                )
            )
            stack.enter_context(self._mock_prediction_dependencies())

            response = self.client.get("/upcoming?league=Bundesliga")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured.get("league_codes"), ["BL1"])

        payload = response.get_json()
        self.assertIn("matches", payload)
        self.assertEqual(len(payload["matches"]), 1)
        self.assertEqual(payload["matches"][0]["league_code"], "BL1")
        self.assertEqual(payload["source"], "The Odds API")

    def test_upcoming_unknown_league_returns_warning(self):
        with patch(
            "football_predictor.app.get_upcoming_matches_with_odds",
            side_effect=APIError("OddsAPI", "NO_DATA", "not found"),
        ):
            response = self.client.get("/upcoming?league=UnknownLeague")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["matches"], [])
        self.assertEqual(payload["source"], "odds_unavailable")
        self.assertEqual(payload["warning"], "odds_unavailable_for_league")


if __name__ == "__main__":
    unittest.main()
