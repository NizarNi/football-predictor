import logging
import unittest
import uuid
from unittest.mock import patch

from football_predictor.logging_utils import reset_warn_once_cache
from football_predictor.xg_data_fetcher import (
    clear_request_memo_id,
    compute_rolling_xg,
    get_team_recent_xg_snapshot,
    set_request_memo_id,
)


class RollingXGTests(unittest.TestCase):
    def setUp(self):
        self.request_id = uuid.uuid4().hex
        set_request_memo_id(self.request_id)
        reset_warn_once_cache()

    def tearDown(self):
        clear_request_memo_id()

    def test_compute_filters_to_league_matches(self):
        logs = [
            {"date": "2024-09-10", "xg_for": 1.2, "xg_against": 0.5, "result": "W", "gameweek": 5},
            {"date": "2024-09-05", "xg_for": 0.7, "xg_against": 1.1, "result": "L", "gameweek": 4},
            {"date": "2024-09-01", "xg_for": 1.0, "xg_against": 0.9, "result": "D", "gameweek": 3},
            {"date": "2024-08-25", "xg_for": 0.5, "xg_against": 0.8, "result": "W", "gameweek": None},
            {"date": "2024-08-20", "xg_for": 0.4, "xg_against": 0.6, "result": None, "gameweek": 2},
        ]
        xg_for_sum, xg_against_sum, window_len, source = compute_rolling_xg(logs, N=2)
        self.assertEqual(window_len, 2)
        self.assertAlmostEqual(xg_for_sum, 1.2 + 0.7)
        self.assertAlmostEqual(xg_against_sum, 0.5 + 1.1)
        self.assertEqual(source, "match_logs")

    @patch("football_predictor.xg_data_fetcher.fetch_league_xg_stats")
    @patch("football_predictor.xg_data_fetcher.fetch_team_match_logs")
    def test_snapshot_memoization_and_warnings(self, mock_logs, mock_league):
        logs = [
            {"date": "2024-09-12", "xg_for": 1.5, "xg_against": 0.6, "result": "W", "gameweek": 4},
            {"date": "2024-09-05", "xg_for": 0.8, "xg_against": 1.0, "result": "D", "gameweek": 3},
            {"date": "2024-08-30", "xg_for": 0.9, "xg_against": 0.7, "result": "W", "gameweek": 2},
        ]
        mock_logs.return_value = logs
        mock_league.return_value = {}

        with self.assertLogs("football_predictor.xg_data_fetcher", level="INFO") as capture:
            first_snapshot = get_team_recent_xg_snapshot("Team Foo", "PL", season=2024, window=5)
            second_snapshot = get_team_recent_xg_snapshot("Team Foo", "PL", season=2024, window=5)

        self.assertEqual(mock_logs.call_count, 1)
        self.assertEqual(first_snapshot, second_snapshot)

        warn_msgs = [
            record.getMessage()
            for record in capture.records
            if record.levelno == logging.WARNING
        ]
        self.assertEqual(len(warn_msgs), 1)
        self.assertIn("partial window 3/5", warn_msgs[0])

        info_msgs = [
            record.getMessage()
            for record in capture.records
            if record.levelno == logging.INFO and "xg_logs:" in record.getMessage()
        ]
        self.assertEqual(len(info_msgs), 1)
        self.assertIn("Team Foo", info_msgs[0])

    @patch("football_predictor.xg_data_fetcher.fetch_team_match_logs", return_value=[])
    @patch("football_predictor.xg_data_fetcher.fetch_league_xg_stats")
    def test_snapshot_falls_back_to_season_table(self, mock_league, _mock_logs):
        mock_league.return_value = {
            "Team Bar": {
                "xg_for_per_game": 1.4,
                "xg_against_per_game": 1.1,
                "matches_played": 8,
            }
        }
        snapshot = get_team_recent_xg_snapshot("Team Bar", "PL", season=2024, window=5)
        self.assertEqual(snapshot["source"], "season")
        self.assertEqual(snapshot["window_len"], 5)
        self.assertAlmostEqual(snapshot["xg_for_sum"], 1.4 * 5)
        self.assertAlmostEqual(snapshot["xg_against_sum"], 1.1 * 5)


if __name__ == "__main__":
    unittest.main()
