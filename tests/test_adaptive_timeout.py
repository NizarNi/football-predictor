import pytest
import logging
from unittest.mock import patch, MagicMock
from football_predictor.app_utils import AdaptiveTimeoutController

@pytest.fixture
def controller():
    """Fixture providing a fresh AdaptiveTimeoutController for each test."""
    return AdaptiveTimeoutController(base_timeout=5, max_timeout=20, increase_factor=2.0, recovery_rate=0.8)

def test_initial_timeout_value(controller):
    """The controller starts with its base timeout."""
    assert controller.get_timeout() == 5

def test_timeout_increases_on_failure(controller):
    """Timeout should increase on repeated failures but never exceed max."""
    controller.record_failure()
    assert controller.get_timeout() == 10
    controller.record_failure()
    assert controller.get_timeout() == 20  # capped at max
    controller.record_failure()
    assert controller.get_timeout() == 20  # no further increase beyond max

def test_timeout_decreases_on_success(controller):
    """Timeout should recover gradually after success."""
    controller.timeout = 15
    controller.record_success()
    assert 11.5 <= controller.get_timeout() <= 12.5  # recovery_rate applied

def test_timeout_stays_above_base(controller):
    """Timeout never drops below base value."""
    controller.timeout = 5
    controller.record_success()
    assert controller.get_timeout() == 5

def test_logging_occurs_on_adjustment(controller, caplog):
    """Log messages should be emitted on both increase and decrease."""
    caplog.set_level(logging.INFO)
    controller.record_failure()
    assert any("[AdaptiveTimeout]" in msg for msg in caplog.messages)
    controller.record_success()
    assert any("Reduced timeout" in msg for msg in caplog.messages)

@patch("football_predictor.app_utils.time.time", return_value=1234567890)
def test_last_adjustment_timestamp(mock_time, controller):
    """Ensure controller stores internal timestamps when adjusting."""
    before = controller._last_adjustment
    controller.record_failure()
    after = controller._last_adjustment
    assert after >= before

