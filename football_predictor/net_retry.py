"""Networking retry helpers shared across HTTP clients."""
from __future__ import annotations

from typing import Any, Iterable, Optional

import contextlib
import requests

from .utils import create_retry_session, request_with_retries as _request_with_retries


@contextlib.contextmanager
def _managed_session(
    session: Optional[requests.Session],
    *,
    retries: int,
    backoff_factor: float,
    status_forcelist: Iterable[int] | None,
) -> Iterable[requests.Session]:
    """Yield a session, creating a temporary one when needed."""

    if session is None:
        managed = create_retry_session(
            max_retries=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
        )
        try:
            yield managed
        finally:
            managed.close()
    else:
        yield session


def request_with_retries(
    *,
    method: str,
    url: str,
    timeout: float,
    retries: int,
    backoff_factor: float,
    status_forcelist: Iterable[int] | None,
    logger,
    context: str,
    session: Optional[requests.Session] = None,
    sanitize: Optional[Any] = None,
    **kwargs: Any,
) -> requests.Response:
    """Wrapper around :func:`utils.request_with_retries` using a managed session."""

    with _managed_session(
        session,
        retries=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    ) as active_session:
        return _request_with_retries(
            active_session,
            method,
            url,
            timeout=timeout,
            max_retries=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            logger=logger,
            context=context,
            sanitize=sanitize,
            **kwargs,
        )


__all__ = ["request_with_retries"]
