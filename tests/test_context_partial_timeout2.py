import pytest
import json
from unittest.mock import patch

from football_predictor.app import app
from football_predictor.utils import TEAM_LOGO_OVERRIDES
from football_predictor.config import API_TIMEOUT_CONTEXT


@pytest.fixture
def client():
    """Provide a Flask test client."""
    app.testing = True
    return app.test_client()


def test_context_accepts_missing_team_params(client):
    """Context endpoint should accept requests without team parameters."""
    with patch("football_predictor.understat_client.fetch_understat_standings") as mock_understat:
        mock_understat.return_value = []

        resp = client.get("/match/test/context?league=EPL")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "ok"

    # Legacy shape: context fields are at the top level (no nested 'context')
    assert "home_team" in payload["data"]
    assert payload["data"].get("home_logo") == TEAM_LOGO_OVERRIDES["default"]


def test_context_returns_full_data_on_time(client):
    """✅ Should return full response when both APIs finish before timeout."""
    with patch("football_predictor.understat_client.fetch_understat_standings") as mock_understat, \
         patch("football_predictor.elo_client.get_team_elo") as mock_elo:

        mock_understat.return_value = [{"name": "Chelsea", "xGA": 25.0, "played": 10}]
        mock_elo.return_value = 1600

        resp = client.get("/match/test/context?league=EPL&home_team=Chelsea&away_team=Arsenal")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "ok"
        assert "home_team" in data["data"]
        assert "away_team" in data["data"]
        assert "partial" not in data["data"]
        assert "xGA" in json.dumps(data)
        assert data["data"].get("home_logo")
        assert data["data"].get("away_logo")


def test_context_returns_partial_when_one_source_times_out(client):
    """⚙️ Should return partial=True when one future exceeds timeout."""
    with patch("football_predictor.understat_client.fetch_understat_standings") as mock_understat, \
         patch("football_predictor.elo_client.get_team_elo") as mock_elo:

        def slow_understat(*args, **kwargs):
            import time
            time.sleep(API_TIMEOUT_CONTEXT + 2)
            return [{"name": "Chelsea", "xGA": 25.0, "played": 10}]

        mock_understat.side_effect = slow_understat
        mock_elo.return_value = 1600

        resp = client.get("/match/test/context?league=EPL&home_team=Chelsea&away_team=Arsenal")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "ok"
        context = data["data"]
        assert context.get("partial") is True
        assert "understat" in context.get("missing", [])
        assert "warning" in context
        assert context.get("home_logo")
        assert context.get("away_logo")


def test_context_returns_partial_when_both_fail(client):
    """🚨 Should gracefully return partial with both sources missing."""
    with patch("football_predictor.understat_client.fetch_understat_standings", side_effect=TimeoutError("Simulated timeout")), \
         patch("football_predictor.elo_client.get_team_elo", side_effect=TimeoutError("Simulated timeout")):

        resp = client.get("/match/test/context?league=EPL&home_team=Chelsea&away_team=Arsenal")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "ok"
        context = data["data"]
        assert context.get("partial") is True
        assert set(context.get("missing", [])) == {"understat", "elo"}
        assert context.get("source") == "partial_timeout"
        assert "warning" in context
        assert context.get("home_logo")
        assert context.get("away_logo")


def test_context_endpoint_never_crashes(client):
    """Endpoint should always return JSON with a status field."""
    resp = client.get("/match/xyz/context?league=EPL")

    assert resp.status_code in (200, 500)
    payload = resp.get_json()
    assert isinstance(payload, dict)
    assert "status" in payload


def test_context_logs_timeout_message(client, caplog):
    """🧾 Log must contain [ContextFetcher] Timeout when fallback triggered."""
    with patch("football_predictor.understat_client.fetch_understat_standings", side_effect=TimeoutError("Simulated timeout")), \
         patch("football_predictor.elo_client.get_team_elo", return_value=1600):

        caplog.set_level("INFO")
        client.get("/match/test/context?league=EPL&home_team=Chelsea&away_team=Arsenal")

        assert any("[ContextFetcher]" in msg for msg in caplog.messages)
        assert any("Timeout" in msg for msg in caplog.messages)
