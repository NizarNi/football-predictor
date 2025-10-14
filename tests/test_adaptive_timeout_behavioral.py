import pytest
import logging
from unittest.mock import patch, MagicMock
from football_predictor.app_utils import AdaptiveTimeoutController

@pytest.fixture
def adaptive_controller():
    """Fixture providing a shared AdaptiveTimeoutController for simulation."""
    return AdaptiveTimeoutController(base_timeout=5, max_timeout=20, increase_factor=2.0, recovery_rate=0.8)

@patch("requests.get")
def test_adaptive_timeout_behavior(mock_get, adaptive_controller, caplog):
    """
    Simulate fluctuating network conditions to test dynamic timeout scaling.
    
    Sequence:
      - 2 timeouts -> increases timeout
      - 3 successes -> gradual recovery
      - 1 more failure -> increases again
    """

    # Prepare mocks for success / failure
    def make_timeout(*args, **kwargs):
        raise Exception("Simulated network timeout")

    def make_success(*args, **kwargs):
        response = MagicMock()
        response.status_code = 200
        return response

    caplog.set_level(logging.INFO)
    initial_timeout = adaptive_controller.get_timeout()

    # Simulate 2 failures
    mock_get.side_effect = make_timeout
    for _ in range(2):
        try:
            mock_get("https://fakeapi.com", timeout=adaptive_controller.get_timeout())
        except Exception:
            adaptive_controller.record_failure()

    after_failures = adaptive_controller.get_timeout()
    assert after_failures > initial_timeout

    # Simulate 3 successes (recovery)
    mock_get.side_effect = make_success
    for _ in range(3):
        resp = mock_get("https://fakeapi.com", timeout=adaptive_controller.get_timeout())
        assert resp.status_code == 200
        adaptive_controller.record_success()

    after_recovery = adaptive_controller.get_timeout()
    assert after_recovery < after_failures
    assert after_recovery >= adaptive_controller.base_timeout

    # Simulate one more failure
    mock_get.side_effect = make_timeout
    try:
        mock_get("https://fakeapi.com", timeout=adaptive_controller.get_timeout())
    except Exception:
        adaptive_controller.record_failure()

    final_timeout = adaptive_controller.get_timeout()
    assert final_timeout > after_recovery

    # Logging assertions
    messages = " ".join(caplog.messages)
    assert "[AdaptiveTimeout]" in messages
    assert "Increased timeout" in messages or "Reduced timeout" in messages

    print("\n[Simulation Summary]")
    print(f"Initial timeout: {initial_timeout}s")
    print(f"After 2 failures: {after_failures}s")
    print(f"After 3 recoveries: {after_recovery}s")
    print(f"After final failure: {final_timeout}s")

