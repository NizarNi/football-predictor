import threading
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

_SENTINEL = object()


class _SimpleCacheBackend:
    def __init__(self, default_timeout: int) -> None:
        self._default_timeout = default_timeout
        self._store: Dict[str, Tuple[Optional[float], Any]] = {}
        self._lock = threading.RLock()

    def _is_expired(self, expires: Optional[float]) -> bool:
        return expires is not None and expires < time.time()

    def get(self, key: str) -> Any:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires, value = entry
            if self._is_expired(expires):
                self._store.pop(key, None)
                return None
            if value is _SENTINEL:
                return None
            return value

    def has(self, key: str) -> bool:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            expires, _ = entry
            if self._is_expired(expires):
                self._store.pop(key, None)
                return False
            return True

    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        timeout = self._default_timeout if timeout is None else timeout
        expires = None if timeout is None else time.time() + timeout
        stored_value = _SENTINEL if value is None else value
        with self._lock:
            self._store[key] = (expires, stored_value)


class Cache:
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        default_timeout = self.config.get("CACHE_DEFAULT_TIMEOUT", 300)
        self.cache = _SimpleCacheBackend(default_timeout)
        self._default_timeout = default_timeout
        self.app = None

    def init_app(self, app: Any) -> None:
        self.app = app

    def memoize(self, timeout: Optional[int] = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            cache_timeout = timeout if timeout is not None else self._default_timeout

            def make_cache_key(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> str:
                key_parts = [func.__module__, func.__qualname__]
                key_parts.extend(repr(arg) for arg in args)
                for key in sorted(kwargs):
                    key_parts.append(f"{key}={repr(kwargs[key])}")
                return "|".join(key_parts)

            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                cache_key = make_cache_key(args, kwargs)
                if self.cache.has(cache_key):
                    cached = self.cache.get(cache_key)
                    return cached
                result = func(*args, **kwargs)
                self.cache.set(cache_key, result, cache_timeout)
                return result

            wrapper.make_cache_key = lambda args, kwargs: make_cache_key(args, kwargs)  # type: ignore[attr-defined]
            wrapper._memoize_timeout = cache_timeout  # type: ignore[attr-defined]
            wrapper.cache = self.cache  # type: ignore[attr-defined]
            return wrapper

        return decorator
