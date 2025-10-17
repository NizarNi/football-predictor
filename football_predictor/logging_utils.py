"""Logging helpers for rate limiting and one-shot warnings."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Iterable, Optional, Tuple


class RateLimitedLogger:
    """Wrapper that rate-limits log messages by an arbitrary key."""

    def __init__(
        self,
        logger: logging.Logger,
        window_seconds: float = 60.0,
    ) -> None:
        self._logger = logger
        self._window = float(max(window_seconds, 0))
        self._last_logged: Dict[Tuple[Any, ...], float] = {}
        self._lock = threading.Lock()

    def _should_emit(self, key: Tuple[Any, ...]) -> bool:
        now = time.monotonic()
        with self._lock:
            last = self._last_logged.get(key)
            if last is not None and (now - last) < self._window:
                return False
            self._last_logged[key] = now
            return True

    def log(self, level: int, key: Iterable[Any], msg: str, *args: Any, **kwargs: Any) -> bool:
        key_tuple = tuple(key)
        if not self._should_emit(key_tuple):
            return False
        self._logger.log(level, msg, *args, **kwargs)
        return True

    def info(self, key: Iterable[Any], msg: str, *args: Any, **kwargs: Any) -> bool:
        return self.log(logging.INFO, key, msg, *args, **kwargs)

    def warning(self, key: Iterable[Any], msg: str, *args: Any, **kwargs: Any) -> bool:
        return self.log(logging.WARNING, key, msg, *args, **kwargs)

    def error(self, key: Iterable[Any], msg: str, *args: Any, **kwargs: Any) -> bool:
        return self.log(logging.ERROR, key, msg, *args, **kwargs)


_warn_once_lock = threading.Lock()
_warned_keys: Dict[Any, bool] = {}


def warn_once(key: Any, msg: str, *, logger: Optional[logging.Logger] = None) -> bool:
    """Emit a warning once per key."""

    with _warn_once_lock:
        if key in _warned_keys:
            return False
        _warned_keys[key] = True

    target_logger = logger or logging.getLogger(__name__)
    target_logger.warning(msg)
    return True


def reset_warn_once_cache() -> None:
    """Test helper to clear the warn-once registry."""

    with _warn_once_lock:
        _warned_keys.clear()

    try:
        from . import xg_data_fetcher
    except Exception:
        return

    if hasattr(xg_data_fetcher, "_PARTIAL_WINDOW_WARNINGS"):
        xg_data_fetcher._PARTIAL_WINDOW_WARNINGS.clear()
