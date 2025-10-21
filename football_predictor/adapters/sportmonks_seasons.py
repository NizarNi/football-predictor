import os
import time
from typing import Optional, Dict, Any, List

import requests

BASE = os.getenv("SPORTMONKS_BASE", "https://api.sportmonks.com/v3/football")
if "SPORTMONKS_KEY" not in os.environ:
    os.environ["SPORTMONKS_KEY"] = ""
TOKEN = os.environ["SPORTMONKS_KEY"]
TIMEOUT = float(os.getenv("SPORTMONKS_TIMEOUT_MS", "5000")) / 1000.0
MIN_SEASON_ID = 1


def _sm_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    p = {"api_token": TOKEN}
    if params:
        p.update(params)
    response = requests.get(f"{BASE}{path}", params=p, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json() or {}


class SeasonResolver:
    """Resolves current or date-appropriate season_id for a league; caches results."""

    def __init__(self, ttl_sec: int = 6 * 3600):
        self.ttl = ttl_sec
        self.cache: Dict[tuple, tuple] = {}  # key=(league_id, anchor_date)->(season_id, expires)

    def _put(self, key, sid: int):
        self.cache[key] = (sid, time.time() + self.ttl)

    def _get(self, key) -> Optional[int]:
        value = self.cache.get(key)
        if not value:
            return None
        sid, expires = value
        if time.time() > expires:
            self.cache.pop(key, None)
            return None
        return sid

    def get_current(self, league_id: int) -> Optional[int]:
        key = (league_id, None)
        sid = self._get(key)
        if sid:
            return sid
        # Best: leagues/{id}?include=currentSeason
        try:
            data = _sm_get(f"/leagues/{league_id}", params={"include": "currentSeason"})
            current = (data.get("data") or {}).get("currentSeason")
            sid_candidate: Optional[int] = None
            if isinstance(current, dict):
                maybe_id = current.get("id")
                if isinstance(maybe_id, int):
                    sid_candidate = maybe_id
                else:
                    nested = current.get("data")
                    if isinstance(nested, dict):
                        maybe_id = nested.get("id")
                        if isinstance(maybe_id, int):
                            sid_candidate = maybe_id
            if isinstance(sid_candidate, int) and sid_candidate >= MIN_SEASON_ID:
                self._put(key, sid_candidate)
                return sid_candidate
        except Exception:
            pass
        # Fallback: newest season for league
        try:
            data = _sm_get(
                "/seasons",
                params={
                    "filters": f"seasonLeagues:{league_id}",
                    "sort": "-id",
                    "per_page": 50,
                },
            )
            rows: List[Dict[str, Any]] = data.get("data") or []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_id = row.get("id")
                if not isinstance(row_id, int) or row_id < MIN_SEASON_ID:
                    continue
                if row.get("is_current") or row.get("active") or row.get("is_active"):
                    self._put(key, row_id)
                    return row_id
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_id = row.get("id")
                if isinstance(row_id, int) and row_id >= MIN_SEASON_ID:
                    self._put(key, row_id)
                    return row_id
        except Exception:
            pass
        return None

    def get_for_date(self, league_id: int, yyyy_mm_dd: str) -> Optional[int]:
        key = (league_id, yyyy_mm_dd)
        sid = self._get(key)
        if sid:
            return sid
        try:
            data = _sm_get(
                "/seasons",
                params={"filters": f"seasonLeagues:{league_id}", "per_page": 100, "sort": "-id"},
            )
            rows: List[Dict[str, Any]] = data.get("data") or []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                start = (row.get("starting_at") or "")[:10]
                end = (row.get("ending_at") or "")[:10]
                row_id = row.get("id")
                if (
                    isinstance(row_id, int)
                    and row_id >= MIN_SEASON_ID
                    and start
                    and end
                    and (start <= yyyy_mm_dd <= end)
                ):
                    self._put(key, row_id)
                    return row_id
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_id = row.get("id")
                if isinstance(row_id, int) and row_id >= MIN_SEASON_ID:
                    self._put(key, row_id)
                    return row_id
        except Exception:
            pass
        return None
