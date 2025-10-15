import copy
import sys
import types
import unittest
from contextlib import ExitStack
from unittest.mock import patch

sys.modules.setdefault("soccerdata", types.ModuleType("soccerdata"))
sys.modules.setdefault("pandas", types.ModuleType("pandas"))

from football_predictor import app as app_module
from football_predictor import config


class TestResponseFormats(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        self.app.testing = True
        self.client = self.app.test_client()
        self._original_flag = config.USE_LEGACY_RESPONSES

    def tearDown(self):
        config.USE_LEGACY_RESPONSES = self._original_flag

    def _mock_match_dependencies(self):
        sample_match = {
            "commence_time": "2024-01-01T12:00:00Z",
            "home_team": "Team A",
            "away_team": "Team B",
            "id": "match-1",
        }
        predictions = {
            "prediction": "HOME_WIN",
            "confidence": 75,
            "probabilities": {
                "HOME_WIN": 0.6,
                "DRAW": 0.25,
                "AWAY_WIN": 0.15,
            },
            "bookmaker_count": 4,
            "best_odds": {"HOME_WIN": 1.8},
            "arbitrage": None,
        }

        stack = ExitStack()
        stack.enter_context(
            patch(
                "football_predictor.app.get_upcoming_matches_with_odds",
                side_effect=lambda *args, **kwargs: [copy.deepcopy(sample_match)],
            )
        )
        stack.enter_context(
            patch(
                "football_predictor.app.calculate_predictions_from_odds",
                return_value=copy.deepcopy(predictions),
            )
        )
        stack.enter_context(
            patch("football_predictor.elo_client.get_team_elo", return_value=1500)
        )
        stack.enter_context(
            patch(
                "football_predictor.elo_client.calculate_elo_probabilities",
                return_value={"home_win": 0.5, "draw": 0.3, "away_win": 0.2},
            )
        )
        return stack

    def test_upcoming_legacy_mode_unwrapped(self):
        config.USE_LEGACY_RESPONSES = True
        with self._mock_match_dependencies():
            response = self.client.get("/upcoming")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        self.assertIn("matches", payload)
        self.assertNotIn("status", payload)
        match = payload["matches"][0]
        self.assertEqual(match["home_logo_url"], "/static/team_logos/generic_shield.svg")
        self.assertEqual(match["away_logo_url"], "/static/team_logos/generic_shield.svg")

    def test_search_legacy_mode_unwrapped(self):
        config.USE_LEGACY_RESPONSES = True
        with self._mock_match_dependencies():
            response = self.client.post("/search", data={"team_name": "Team A"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("matches", payload)
        self.assertNotIn("status", payload)
        match = payload["matches"][0]
        self.assertEqual(match["home_logo_url"], "/static/team_logos/generic_shield.svg")
        self.assertEqual(match["away_logo_url"], "/static/team_logos/generic_shield.svg")

    def test_upcoming_new_mode_wrapped(self):
        config.USE_LEGACY_RESPONSES = False
        with self._mock_match_dependencies():
            response = self.client.get("/upcoming")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("status"), "ok")
        self.assertIn("data", payload)
        self.assertIn("matches", payload["data"])
        match = payload["data"]["matches"][0]
        self.assertEqual(match["home_logo_url"], "/static/team_logos/generic_shield.svg")
        self.assertEqual(match["away_logo_url"], "/static/team_logos/generic_shield.svg")

    def test_search_new_mode_wrapped(self):
        config.USE_LEGACY_RESPONSES = False
        with self._mock_match_dependencies():
            response = self.client.post("/search", data={"team_name": "Team A"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("status"), "ok")
        self.assertIn("data", payload)
        self.assertIn("matches", payload["data"])
        match = payload["data"]["matches"][0]
        self.assertEqual(match["home_logo_url"], "/static/team_logos/generic_shield.svg")
        self.assertEqual(match["away_logo_url"], "/static/team_logos/generic_shield.svg")

    def test_status_endpoint_reports_mode(self):
        config.USE_LEGACY_RESPONSES = True
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["data"]["legacy_mode"])

        config.USE_LEGACY_RESPONSES = False
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload["data"]["legacy_mode"])


if __name__ == "__main__":
    unittest.main()
