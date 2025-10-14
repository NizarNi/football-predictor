import logging
import time
from functools import wraps
from typing import Any, Dict, Optional

from flask import jsonify, request, current_app

from . import config
from .errors import APIError


class AdaptiveTimeoutController:
    """Dynamically adjusts API timeouts based on recent request performance."""

    def __init__(
        self,
        base_timeout: float = 10,
        max_timeout: float = 30,
        increase_factor: float = 1.5,
        recovery_rate: float = 0.95,
    ) -> None:
        self.timeout = base_timeout
        self.base_timeout = base_timeout
        self.max_timeout = max_timeout
        self.increase_factor = increase_factor
        self.recovery_rate = recovery_rate
        self.logger = logging.getLogger(__name__)
        self._last_adjustment = time.time()
        self._last_monitor_log = time.time()
        self._success_count = 0
        self._failure_count = 0
        self._last_failure_timestamp: float | None = None

    def record_failure(self) -> None:
        """Increase timeout after a failure, up to the max."""

        self._failure_count += 1
        self._last_failure_timestamp = time.time()
        old_timeout = self.timeout
        self.timeout = min(self.timeout * self.increase_factor, self.max_timeout)
        self.logger.warning(
            "[AdaptiveTimeout] Increased timeout from %.1fs to %.1fs",
            old_timeout,
            self.timeout,
        )
        self._maybe_log_summary()

    def record_success(self) -> None:
        """Gradually recover timeout back toward the base."""

        self._success_count += 1
        if self.timeout > self.base_timeout:
            old_timeout = self.timeout
            self.timeout = max(self.base_timeout, self.timeout * self.recovery_rate)
            if abs(old_timeout - self.timeout) > 0.5:
                self.logger.info(
                    "[AdaptiveTimeout] Reduced timeout from %.1fs to %.1fs",
                    old_timeout,
                    self.timeout,
                )
        self._maybe_log_summary()

    def get_timeout(self) -> float:
        """Return current adaptive timeout value."""

        return self.timeout

    def get_metrics(self) -> Dict[str, Any]:
        """Return resilience metrics for monitoring endpoints."""

        total = self._success_count + self._failure_count
        success_rate = (self._success_count / total) if total else 1.0
        last_failure_iso: Optional[str] = None
        if self._last_failure_timestamp is not None:
            last_failure_iso = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._last_failure_timestamp)
            )
        return {
            "current_timeout": round(self.timeout, 2),
            "success_rate": round(success_rate, 4),
            "failures": self._failure_count,
            "successes": self._success_count,
            "last_failure": last_failure_iso,
        }

    def _maybe_log_summary(self) -> None:
        """Emit periodic resilience summary logs."""

        now = time.time()
        if now - self._last_monitor_log < 600:
            return

        metrics = self.get_metrics()
        self.logger.info(
            "[ResilienceMonitor] Timeout=%.1fs, Failures=%d, SuccessRate=%d%%",
            metrics["current_timeout"],
            metrics["failures"],
            int(metrics["success_rate"] * 100),
        )
        self._last_monitor_log = now

# Routes that must continue returning legacy (unwrapped) JSON so the
# front-end can consume the responses without modifications.
_LEGACY_EXACT_PATHS = {
    "/upcoming",
    "/search",
    "/career_xg",
}

# All nested `/match/...` endpoints previously returned unwrapped payloads.
_LEGACY_PREFIXES = ("/match/",)


def legacy_endpoint(func):
    """Decorator to explicitly mark a route as legacy-only."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    setattr(func, "_legacy_endpoint", True)
    setattr(wrapper, "_legacy_endpoint", True)
    return wrapper


def _is_legacy_request() -> bool:
    """Determine if the current request should return legacy JSON."""
    if not getattr(config, "USE_LEGACY_RESPONSES", True):
        return False

    try:
        path = request.path  # type: ignore[attr-defined]
    except RuntimeError:
        # Outside of a request context (e.g., during CLI usage or tests),
        # default to wrapped responses.
        return False

    if not path:
        return False

    # Modernized match-context endpoint should always use wrapped responses.
    if path.startswith("/match/") and path.endswith("/context"):
        return False

    endpoint = None
    try:
        endpoint = request.endpoint  # type: ignore[attr-defined]
    except RuntimeError:
        endpoint = None

    view_func = None
    if endpoint:
        try:
            app = current_app._get_current_object()  # type: ignore[attr-defined]
        except RuntimeError:
            app = None
        if app is not None:
            view_func = app.view_functions.get(endpoint)

    if view_func and getattr(view_func, "_legacy_endpoint", False):
        return True

    if path in _LEGACY_EXACT_PATHS:
        return True

    return any(path.startswith(prefix) for prefix in _LEGACY_PREFIXES)


def _build_success_payload(data: Optional[Any], message: str) -> Dict[str, Any] | Any:
    """Construct success payload, wrapping unless legacy route."""
    if _is_legacy_request():
        # Legacy endpoints historically returned the raw data structure.
        return data if data is not None else {}

    return {
        "status": "ok",
        "message": message,
        "data": data,
    }


def _build_error_payload(error: Any, message: str) -> Dict[str, Any] | Any:
    """Construct error payload, wrapping unless legacy route."""
    if _is_legacy_request():
        legacy_payload = {"error": error}
        if message:
            legacy_payload["message"] = message
        return legacy_payload

    return {
        "status": "error",
        "message": message,
        "error": error,
    }


def make_ok(data: Optional[Any] = None, message: str = "success", status_code: int = 200):
    """Return a standardized success response (legacy-aware)."""
    payload = _build_success_payload(data, message)
    response = jsonify(payload)
    return response, status_code


def make_error(error: Any, message: str = "An error occurred", status_code: int = 400):
    """Return a standardized error response (legacy-aware)."""
    if isinstance(error, APIError):
        error = error.to_dict()

    payload = _build_error_payload(error, message)
    response = jsonify(payload)
    return response, status_code
