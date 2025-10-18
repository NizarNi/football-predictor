import json
import sys
import types
import unittest
from unittest.mock import patch

if "pandas" not in sys.modules:
    pandas_stub = types.ModuleType("pandas")
    pandas_stub.Series = tuple
    pandas_stub.isna = lambda value: value is None
    sys.modules["pandas"] = pandas_stub

if "soccerdata" not in sys.modules:
    class _FBrefStub:
        def __init__(self, *args, **kwargs):
            pass

    soccerdata_stub = types.ModuleType("soccerdata")
    soccerdata_stub.FBref = _FBrefStub
    sys.modules["soccerdata"] = soccerdata_stub

if "understat" not in sys.modules:
    class _UnderstatStub:
        async def get_league_table(self, *args, **kwargs):
            return []

    understat_stub = types.ModuleType("understat")
    understat_stub.Understat = lambda *args, **kwargs: _UnderstatStub()
    sys.modules["understat"] = understat_stub

if "aiohttp" not in sys.modules:
    class _ClientSessionStub:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    aiohttp_stub = types.ModuleType("aiohttp")
    aiohttp_stub.ClientSession = _ClientSessionStub
    sys.modules["aiohttp"] = aiohttp_stub

from football_predictor.app import app as flask_app


class BTTSTests(unittest.TestCase):
    def setUp(self):
        self.client = flask_app.test_client()

    @patch("football_predictor.odds_calculator.calculate_btts_probability_from_xg")
    @patch("football_predictor.odds_calculator.calculate_btts_from_odds", return_value={"odds": []})
    @patch(
        "football_predictor.odds_api_client.get_event_odds",
        return_value={"bookmakers": [{"markets": []}]},
    )
    @patch("football_predictor.app.get_match_xg_prediction")
    @patch("football_predictor.app.get_current_season", return_value=2024)
    @patch("football_predictor.understat_client.fetch_understat_standings")
    @patch("football_predictor.app.resolve_team_name", side_effect=lambda name, provider=None: name)
    @patch("football_predictor.app.fuzzy_team_match", side_effect=lambda a, b: a == b)
    @patch("football_predictor.app.get_team_recent_xg_snapshot")
    def test_btts_uses_recent_xg_context(
        self,
        mock_recent,
        mock_fuzzy,
        mock_resolve,
        mock_understat,
        mock_season,
        mock_xg_prediction,
        mock_odds,
        mock_market,
        mock_prob,
    ):
        home_snapshot = {
            "team": "Home FC",
            "xg_for_sum": 6.0,
            "xg_against_sum": 4.5,
            "window_len": 3,
            "source": "season",
            "season": 2024,
        }
        away_snapshot = {
            "team": "Away FC",
            "xg_for_sum": 4.5,
            "xg_against_sum": 3.0,
            "window_len": 3,
            "source": "season",
            "season": 2024,
        }
        mock_recent.side_effect = [home_snapshot, away_snapshot]
        mock_understat.return_value = [
            {"name": "Home FC", "xGA": 6.0, "played": 3},
            {"name": "Away FC", "xGA": 4.5, "played": 3},
        ]
        mock_xg_prediction.return_value = {"available": False}

        mock_prob.return_value = {
            "yes_probability": 0.62,
            "no_probability": 0.38,
            "confidence": "medium",
            "reasoning": "test",
        }

        response = self.client.get(
            "/match/123/btts",
            query_string={
                "sport_key": "soccer_epl",
                "home_team": "Home FC",
                "away_team": "Away FC",
                "league": "PL",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertIn("btts", payload)
        self.assertEqual(mock_recent.call_count, 2)

        context_header = response.headers.get("X-Server-Context")
        self.assertIsNotNone(context_header)
        context = json.loads(context_header)
        self.assertAlmostEqual(context["team_recent_xg_for"], 2.0)
        self.assertAlmostEqual(context["opp_recent_xg_for"], 1.5)
        self.assertEqual(context["recent_xg_window_len"], 3)

    @patch("football_predictor.odds_calculator.calculate_btts_probability_from_xg")
    @patch("football_predictor.odds_calculator.calculate_btts_from_odds", return_value={"odds": []})
    @patch(
        "football_predictor.odds_api_client.get_event_odds",
        return_value={"bookmakers": [{"markets": []}]},
    )
    @patch("football_predictor.app.get_team_recent_xg_snapshot", side_effect=[
        {
            "team": "Home FC",
            "xg_for_sum": 5.0,
            "xg_against_sum": 4.0,
            "window_len": 5,
            "source": "season",
            "season": 2024,
        },
        {
            "team": "Away FC",
            "xg_for_sum": 4.5,
            "xg_against_sum": 3.5,
            "window_len": 5,
            "source": "season",
            "season": 2024,
        },
    ])
    @patch("football_predictor.app.get_match_xg_prediction", return_value={"available": False})
    @patch("football_predictor.app.get_current_season", return_value=2024)
    @patch("football_predictor.understat_client.fetch_understat_standings", return_value=[])
    @patch("football_predictor.app.resolve_team_name", side_effect=lambda name, provider=None: name)
    @patch("football_predictor.app.fuzzy_team_match", side_effect=lambda a, b: a == b)
    def test_btts_handles_season_fallback(
        self,
        mock_fuzzy,
        mock_resolve,
        mock_understat,
        mock_season,
        mock_xg_prediction,
        mock_recent,
        mock_odds,
        mock_market,
        mock_prob,
    ):
        mock_prob.return_value = {"yes_probability": 0.5}
        response = self.client.get(
            "/match/456/btts",
            query_string={
                "sport_key": "soccer_epl",
                "home_team": "Home FC",
                "away_team": "Away FC",
                "league": "PL",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("btts", payload)
        self.assertIn("xg_model", payload["btts"])
        self.assertEqual(mock_recent.call_count, 2)
        context_header = response.headers.get("X-Server-Context")
        self.assertIsNotNone(context_header)
        context = json.loads(context_header)
        self.assertEqual(context.get("recent_xg_window_len"), 5)
        mock_prob.assert_called_once()


if __name__ == "__main__":
    unittest.main()
