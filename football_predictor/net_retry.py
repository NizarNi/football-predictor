# football_predictor/net_retry.py
"""Centralized retry helper for network requests (shared across clients)."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Iterable, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import requests
from requests import Response

from .config import setup_logger
from .utils import create_retry_session, request_with_retries as _request_with_retries

_logger = setup_logger(__name__)


def _normalize_status_list(status_forcelist: Iterable[int] | None) -> Tuple[int, ...]:
    if not status_forcelist:
        return tuple()
    return tuple(sorted(set(int(s) for s in status_forcelist)))


def _scrub_url(url: Optional[str]) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        # strip querystring for logs
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    except Exception:
        return url or ""


@lru_cache(maxsize=16)
def _get_session(
    retries: int,
    backoff_factor: float,
    status_forcelist: Tuple[int, ...],
) -> requests.Session:
    # Create a requests.Session with mounted HTTPAdapter/Retry
    return create_retry_session(
        max_retries=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )


def request_with_retries(
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: Iterable[int] | None = (429, 500, 502, 503, 504),
    timeout: float = 5.0,
    logger=None,
    context: Optional[str] = None,
    sanitize: Optional[Any] = None,
    attempt_log_level: int | None = logging.DEBUG,
    failure_log_level: int = logging.WARNING,
    session: Optional[Any] = None,  # allow facade with .request(...)
    **kwargs: Any,
) -> Response:
    """
    Perform an HTTP request with shared retry/backoff.
    - If `session` is provided (incl. a facade), it's used as-is.
    - Otherwise a cached retry-configured requests.Session is used.
    - Forwards to utils.request_with_retries(session, method, url, ...).
    """
    normalized_statuses = _normalize_status_list(status_forcelist)
    session_obj = session or _get_session(retries, backoff_factor, normalized_statuses)
    active_logger = logger or _logger
    sanitize_fn = sanitize or (lambda value: _scrub_url(str(value)))

    return _request_with_retries(
        session_obj,
        method,
        url,
        timeout=timeout,
        max_retries=retries,         # NOTE: underlying util expects max_retries
        backoff_factor=backoff_factor,
        status_forcelist=normalized_statuses,
        logger=active_logger,
        context=context or f"{method} {url}",
        sanitize=sanitize_fn,
        attempt_log_level=attempt_log_level,
        failure_log_level=failure_log_level,
        **kwargs,
    )


__all__ = ["request_with_retries"]
