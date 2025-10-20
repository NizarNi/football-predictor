from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import time
import threading
import logging

import requests

from ..ports.fixtures import FixturesPort, Fixture
from ..ports.lineups import LineupsPort, Lineups  # stubs for later
from ..ports.standings import StandingsPort, Standings  # stubs for later
from ..settings import SPORTMONKS_KEY, SPORTMONKS_BASE, SPORTMONKS_TIMEOUT_MS
from ..constants import sportmonks_league_id
from ..fotmob_shared import to_iso_utc, normalize_team_dict

log = logging.getLogger(__name__)


class _TTL:
    """A tiny thread-safe TTL cache for Sportmonks responses."""

    def __init__(self) -> None:
        self._d: Dict[Tuple[Any, ...], Tuple[float, Any]] = {}
        self._l = threading.Lock()

    def get(self, key: Tuple[Any, ...], ttl: float) -> Any:
        now = time.time()
        with self._l:
            value = self._d.get(key)
            if not value:
                return None
            ts, data = value
            if now - ts > ttl:
                self._d.pop(key, None)
                return None
            return data

    def set(self, key: Tuple[Any, ...], value: Any) -> None:
        with self._l:
            self._d[key] = (time.time(), value)


_cache = _TTL()


def _session() -> requests.Session:
    session = requests.Session()
    session.params.update({"api_token": SPORTMONKS_KEY or ""})
    session.headers.update({"Accept": "application/json"})
    return session


def _ymd(iso: str) -> str:
    """Extract YYYY-MM-DD from an ISO timestamp."""

    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return iso[:10]


def _map_status(state: Dict[str, Any]) -> Tuple[str, Optional[int]]:
    """Map Sportmonks state info to our status/minute."""

    name = (state or {}).get("short_name") or (state or {}).get("name") or ""
    name = str(name).upper()
    minute: Optional[int] = None
    if name in {"NS", "NOT STARTED"}:
        return "NS", None
    if name in {"FT", "FULL-TIME", "AET"}:
        return "FT", None
    if name in {"HT", "HALF-TIME"}:
        return "HT", None
    if name in {"LIVE", "1ST HALF", "2ND HALF"}:
        return "LIVE", minute
    return name or "NS", minute


class SportmonksAdapter(FixturesPort, LineupsPort, StandingsPort):
    def __init__(self, timeout_ms: Optional[int] = None) -> None:
        self.timeout = (timeout_ms or SPORTMONKS_TIMEOUT_MS) / 1000.0

    # -------- FixturesPort --------
    def get_fixtures(self, competition_code: str, start_iso: str, end_iso: str) -> List[Fixture]:
        league_id = sportmonks_league_id(competition_code)
        if not league_id or not SPORTMONKS_KEY:
            return []

        cache_key = ("sportmonks_fixtures", league_id, start_iso, end_iso)
        cached = _cache.get(cache_key, ttl=60.0)
        if cached is not None:
            return cached

        date_from = _ymd(start_iso)
        date_to = _ymd(end_iso)

        url = f"{SPORTMONKS_BASE}/fixtures/between/{date_from}/{date_to}"
        params = {
            "filters": f"league_id:{league_id}",
            "include": "participants;scores;state",
        }

        session = _session()
        items: List[Fixture] = []

        try:
            response = session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json().get("data", [])
        except Exception as exc:  # pragma: no cover - network dependent
            log.warning("sportmonks_fixtures_failed lid=%s err=%s", league_id, exc)
            data = []

        for fx in data:
            fixture_id = fx.get("id")
            dt_iso = fx.get("starting_at") or fx.get("starting_at_timestamp")
            kickoff_iso: Optional[str] = None
            if isinstance(dt_iso, str):
                try:
                    ko_dt = datetime.fromisoformat(dt_iso.replace("Z", "+00:00")).astimezone(timezone.utc)
                    kickoff_iso = to_iso_utc(ko_dt)
                except Exception:
                    kickoff_iso = None
            elif isinstance(dt_iso, (int, float)):
                try:
                    ko_dt = datetime.fromtimestamp(int(dt_iso), tz=timezone.utc)
                    kickoff_iso = to_iso_utc(ko_dt)
                except Exception:
                    kickoff_iso = None

            if not (fixture_id and kickoff_iso):
                continue

            participants = fx.get("participants") or []
            home_raw: Dict[str, Any] = {}
            away_raw: Dict[str, Any] = {}
            for participant in participants:
                location = str(participant.get("meta", {}).get("location", "")).lower()
                if location == "home":
                    home_raw = participant.get("participant", {}) or {}
                    if "scores" in participant:
                        home_raw["score"] = (participant.get("scores") or {}).get("total")
                elif location == "away":
                    away_raw = participant.get("participant", {}) or {}
                    if "scores" in participant:
                        away_raw["score"] = (participant.get("scores") or {}).get("total")

            home = normalize_team_dict(
                {
                    "id": home_raw.get("id"),
                    "name": home_raw.get("name"),
                    "score": home_raw.get("score"),
                }
            )
            away = normalize_team_dict(
                {
                    "id": away_raw.get("id"),
                    "name": away_raw.get("name"),
                    "score": away_raw.get("score"),
                }
            )

            status, minute = _map_status(fx.get("state") or {})

            items.append(
                {
                    "match_id": str(fixture_id),
                    "competition": competition_code,
                    "competition_code": competition_code,
                    "kickoff_iso": kickoff_iso,
                    "status": status,
                    "minute": minute,
                    "home": home,
                    "away": away,
                }
            )

        try:
            items.sort(key=lambda item: item["kickoff_iso"])
        except Exception:
            pass

        _cache.set(cache_key, items)
        return items

    # -------- Stubs (to be implemented later) --------
    def get_lineups(self, match_id: str) -> Lineups:
        return {
            "match_id": str(match_id),
            "home": {"team_id": 0, "team_name": "", "formation": None, "starters": [], "bench": []},
            "away": {"team_id": 0, "team_name": "", "formation": None, "starters": [], "bench": []},
        }

    def get_standings(self, competition_code: str, season: str) -> Standings:
        return {"competition_code": competition_code, "season": season, "table": []}
