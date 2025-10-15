"""Centralized retry helper for network requests."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterable, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import requests
from requests import Response

from .config import setup_logger
from .utils import create_retry_session, request_with_retries as _request_with_retries

_logger = setup_logger(__name__)


def _normalize_status_list(status_forcelist: Iterable[int]) -> Tuple[int, ...]:
    return tuple(sorted(set(status_forcelist)))


def _scrub_url(url: Optional[str]) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    except Exception:
        return url


@lru_cache(maxsize=16)
def _get_session(
    retries: int,
    backoff_factor: float,
    status_forcelist: Tuple[int, ...],
) -> requests.Session:
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
    status_forcelist: Iterable[int] = (429, 500, 502, 503, 504),
    timeout: float = 5,
    logger=None,
    context: Optional[str] = None,
    sanitize=None,
    attempt_log_level: int | None = logging.DEBUG,
    failure_log_level: int = logging.WARNING,
    session: Optional[requests.Session] = None,
    **kwargs,
) -> Response:
    """Perform an HTTP request with retry behaviour shared across clients."""

    normalized_statuses = _normalize_status_list(status_forcelist)
    session_obj = session or _get_session(retries, backoff_factor, normalized_statuses)
    active_logger = logger or _logger

    sanitize_fn = sanitize or (lambda value: _scrub_url(str(value)))

    return _request_with_retries(
        session_obj,
        method,
        url,
        timeout=timeout,
        max_retries=retries,
        backoff_factor=backoff_factor,
        status_forcelist=normalized_statuses,
        logger=active_logger,
        context=context or f"{method} {url}",
        sanitize=sanitize_fn,
        attempt_log_level=attempt_log_level,
        failure_log_level=failure_log_level,
        **kwargs,
    )

