from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import time
import threading
import logging
from urllib.parse import urlparse

import requests

from ..ports.fixtures import FixturesPort, Fixture
from ..ports.lineups import LineupsPort, Lineups  # stubs for later
from ..ports.standings import StandingsPort, Standings  # stubs for later
from ..settings import SPORTMONKS_KEY, SPORTMONKS_BASE, SPORTMONKS_TIMEOUT_MS
from ..constants import sportmonks_league_id
from ..fotmob_shared import to_iso_utc, normalize_team_dict

log = logging.getLogger(__name__)


FIXTURE_INCLUDES_FEED = "participants,scores,state"
FIXTURE_INCLUDES_FALLBACK = "participants,scores,state,league"


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


def _is_list_404(path: str, status_code: int) -> bool:
    if status_code != 404:
        return False
    normalized = path.rstrip("/")
    return normalized.endswith("/fixtures") or "/fixtures/between" in normalized


class SportmonksAdapter(FixturesPort, LineupsPort, StandingsPort):
    def __init__(self, timeout_ms: Optional[int] = None) -> None:
        self.timeout = (timeout_ms or SPORTMONKS_TIMEOUT_MS) / 1000.0

    # -------- FixturesPort --------
    def get_fixtures(self, competition_code: str, start_iso: str, end_iso: str) -> List[Fixture]:
        league_id = sportmonks_league_id(competition_code)
        if not SPORTMONKS_KEY:
            log.warning("sportmonks_key_missing")
            return []
        if not league_id:
            log.info("sportmonks_league_unmapped_or_unavailable code=%s", competition_code)
            return []

        cache_key = ("sportmonks_fixtures", league_id, start_iso, end_iso)
        cached = _cache.get(cache_key, ttl=60.0)
        if cached is not None:
            return cached

        date_from = _ymd(start_iso)
        date_to = _ymd(end_iso)

        url = f"{SPORTMONKS_BASE}/fixtures/between/{date_from}/{date_to}"
        params = {
            # v3 expects fixture-level league filter:
            # https://docs.sportmonks.com/football/endpoints-and-entities/entities/fixture
            "filters": f"fixtureLeagues:{league_id}",
            # Includes for feed cards:
            # participants            -> team objects + meta.location (home/away)
            # scores                  -> fixture-level scores by participant_id
            # state                   -> match status
            "include": FIXTURE_INCLUDES_FEED,
        }

        session = _session()
        items: List[Fixture] = []
        path = urlparse(url).path

        try:
            response = session.get(url, params=params, timeout=self.timeout)
        except Exception as exc:  # pragma: no cover - network dependent
            log.warning("sportmonks_fixtures_failed lid=%s err=%s", league_id, exc)
            return []

        if _is_list_404(path, response.status_code):
            log.warning(
                "sportmonks_fixtures_empty lid=%s path=%s status=%s",
                league_id,
                path,
                response.status_code,
            )
            data: List[Dict[str, Any]] = []
        else:
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                log.warning("sportmonks_fixtures_failed lid=%s err=%s", league_id, exc)
                raise

            try:
                payload = response.json()
            except ValueError:
                payload = {}

            data = payload.get("data", []) if isinstance(payload, dict) else []

        # Fallback: retry unfiltered and filter client-side by league id
        did_fallback = False
        if not data:
            try:
                fb_resp = session.get(
                    url,
                    params={"include": FIXTURE_INCLUDES_FALLBACK},
                    timeout=self.timeout,
                )
                if fb_resp.ok:
                    fb_payload = fb_resp.json() or {}
                    fb_data = fb_payload.get("data", []) if isinstance(fb_payload, dict) else []
                    data = [
                        fx
                        for fx in fb_data
                        if (
                            isinstance(fx.get("league"), dict)
                            and fx["league"].get("id") == league_id
                        )
                        or fx.get("league_id") == league_id
                    ]
                    did_fallback = True
                    log.info(
                        "sportmonks_fallback_unfiltered_used lid=%s kept=%d",
                        league_id,
                        len(data),
                    )
            except Exception as exc:
                log.warning("sportmonks_fallback_unfiltered_err lid=%s err=%s", league_id, exc)

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
            scores = fx.get("scores") or []  # list of {participant_id, score, description/type}
            score_by_pid: Dict[Any, Any] = {}
            try:
                for s in scores:
                    pid = s.get("participant_id")
                    sc = s.get("score")
                    if pid is not None and sc is not None:
                        # take "total" or last seen; simple for now
                        score_by_pid[pid] = sc
            except Exception:
                pass

            home_raw: Dict[str, Any] = {}
            away_raw: Dict[str, Any] = {}

            for p in participants:
                meta = (p.get("meta") or {})
                loc = str(meta.get("location", "")).lower()
                # Some responses nest under p['participant']; others keep team fields on p.
                team = p.get("participant") or p or {}
                pid = team.get("id")

                # Attach score if present at participant level or via scores index
                p_score = None
                if isinstance(p.get("scores"), dict):
                    p_score = (p.get("scores") or {}).get("total")
                if p_score is None and pid in score_by_pid:
                    p_score = score_by_pid.get(pid)

                enriched = {
                    "id": pid,
                    "name": team.get("name"),
                    "score": p_score,
                }

                if loc == "home":
                    home_raw = enriched
                elif loc == "away":
                    away_raw = enriched

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

        log.info(
            "sportmonks_fixtures_built code=%s lid=%s count=%d from=%s to=%s",
            competition_code,
            league_id,
            len(items),
            _ymd(start_iso),
            _ymd(end_iso),
            did_fallback,
        )
        _cache.set(cache_key, items)
        return items

    def probe_league(self, league_id: int) -> bool:
        url = f"{SPORTMONKS_BASE}/leagues/{league_id}"
        session = _session()
        try:
            response = session.get(url, timeout=self.timeout)
        except Exception as exc:  # pragma: no cover - network dependent
            log.warning("sportmonks_league_probe_failed lid=%s err=%s", league_id, exc)
            return False

        if response.status_code == 200:
            return True

        if response.status_code in {403, 404}:
            log.warning(
                "sportmonks_league_invisible lid=%s status=%s",
                league_id,
                response.status_code,
            )
            return False

        response.raise_for_status()
        return True

    # -------- Stubs (to be implemented later) --------
    def get_lineups(self, match_id: str) -> Lineups:
        return {
            "match_id": str(match_id),
            "home": {"team_id": 0, "team_name": "", "formation": None, "starters": [], "bench": []},
            "away": {"team_id": 0, "team_name": "", "formation": None, "starters": [], "bench": []},
        }

    def get_standings(self, competition_code: str, season: str) -> Standings:
        return {"competition_code": competition_code, "season": season, "table": []}
