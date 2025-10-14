"""
Adaptive Timeout Demonstration Client
------------------------------------
This stub simulates a live Odds API client that randomly succeeds or fails.
It’s meant only for testing the AdaptiveTimeoutController in Replit logs.

Run with:
    python -m football_predictor.adaptive_client_demo
"""

import random
import time
import logging
import requests
from .config import setup_logger
from .app_utils import AdaptiveTimeoutController

logger = setup_logger(__name__)
adaptive_timeout = AdaptiveTimeoutController(base_timeout=5, max_timeout=25, increase_factor=1.6, recovery_rate=0.9)


def simulate_request_cycle(n_requests: int = 10):
    """Simulate repeated API calls, some successful, some failing."""
    for i in range(1, n_requests + 1):
        url = "https://httpbin.org/delay/2"  # harmless demo endpoint

        # Randomly decide if this call will "fail" (simulate timeout)
        should_fail = random.random() < 0.3
        logger.info(f"[Demo] Starting simulated request {i} (fail={should_fail})")

        try:
            timeout = adaptive_timeout.get_timeout()
            if should_fail:
                # simulate failure by raising Timeout manually
                raise requests.Timeout("Simulated timeout for demonstration")

            # simulate successful request
            time.sleep(random.uniform(0.2, 0.5))
            adaptive_timeout.record_success()
            logger.info(f"[Demo] ✅ Request {i} succeeded (timeout={timeout:.1f}s)")

        except requests.Timeout as e:
            adaptive_timeout.record_failure()
            logger.warning(f"[Demo] ⚠️ Request {i} failed: {e} (new timeout={adaptive_timeout.get_timeout():.1f}s)")

        # small pause between cycles
        time.sleep(0.5)


if __name__ == "__main__":
    logger.info("Starting adaptive timeout demonstration...")
    simulate_request_cycle(n_requests=15)
    logger.info("✅ Demo complete.")

