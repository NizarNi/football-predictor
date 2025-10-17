"""Request-scoped memoization helpers for rolling xG computations."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from . import xg_data_fetcher as _xg

_KEY_PREFIX = "rolling_xg"


def _get_request_bucket() -> Tuple[Optional[str], Optional[Dict[Tuple[Any, ...], Any]]]:
    request_id = _xg.get_current_request_memo_id()
    if not request_id:
        return None, None
    with _xg._request_memo_lock:  # type: ignore[attr-defined]
        bucket = _xg._request_memo_store.setdefault(request_id, {})  # type: ignore[attr-defined]
    return request_id, bucket


def compute_rolling_xg(
    team_logs: Any,
    N: int,
    league_only: bool = True,
    **kwargs: Any,
):
    league = kwargs.get("league")
    season = kwargs.get("season")
    team_identifier = kwargs.get("team_identifier") or kwargs.get("team")
    season_fallback = kwargs.get("season_fallback")
    if season_fallback:
        fallback_key = (
            season_fallback.get("xg_for_per_game"),
            season_fallback.get("xg_against_per_game"),
        )
    else:
        fallback_key = None

    request_id, bucket = _get_request_bucket()
    key = (
        _KEY_PREFIX,
        team_identifier,
        league,
        season,
        int(N),
        bool(league_only),
        fallback_key,
    )

    if bucket is not None:
        cached = bucket.get(key)
        if cached is not None:
            return cached

    result = _xg.compute_rolling_xg(
        team_logs,
        N,
        league_only=league_only,
        league=league,
        season=season,
        team_identifier=team_identifier,
        season_fallback=season_fallback,
    )

    if request_id is not None:
        with _xg._request_memo_lock:  # type: ignore[attr-defined]
            target_bucket = _xg._request_memo_store.setdefault(request_id, {})  # type: ignore[attr-defined]
            target_bucket[key] = result

    return result


__all__ = ["compute_rolling_xg"]

