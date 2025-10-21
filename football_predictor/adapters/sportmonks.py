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


# Lean includes for initial attempt
FIXTURE_INCLUDES_FEED = "participants,scores,state"


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
        date_to   = _ymd(end_iso)
        session   = _session()

        # Doc-faithful Standard path:
        # 1) /seasons?filters=seasonLeagues:{lid}
        # 2) /schedules/seasons/{season_id}  (Include options: NONE)

        seasons: List[Dict[str, Any]] = []
        season_id = None
        try:
            sv = session.get(
                f"{SPORTMONKS_BASE}/seasons",
                params={"api_token": SPORTMONKS_KEY, "filters": f"seasonLeagues:{league_id}"},
                timeout=self.timeout,
            )
            sv.raise_for_status()
            js = sv.json() or {}
            seasons = js.get("data", [])
            if not isinstance(seasons, list):
                seasons = []
        except Exception as exc:
            log.warning("sportmonks_seasons_lookup_err lid=%s err=%s", league_id, exc)

        def _pick_season(rows: List[Dict[str, Any]]) -> Optional[int]:
            cand = [r for r in rows if isinstance(r, dict)]
            if not cand:
                return None
            def is_current(s: Dict[str, Any]) -> bool:
                v = s.get("is_current")
                if isinstance(v, bool):
                    return v
                # other flags sometimes used
                return bool(s.get("current")) or bool(s.get("is_active"))
            cur = [s for s in cand if is_current(s)]
            if cur:
                return cur[0].get("id")
            # fallback: latest by (year, id)
            cand.sort(key=lambda s: (s.get("year") or 0, s.get("id") or 0), reverse=True)
            return cand[0].get("id")

        season_id = _pick_season(seasons)
        if not season_id:
            log.warning("sportmonks_season_missing lid=%s", league_id)
            _cache.set(cache_key, [])
            return []

        # 2) Schedules by Season (NO includes per doc)
        schedules: List[Dict[str, Any]] = []
        try:
            sch = session.get(
                f"{SPORTMONKS_BASE}/schedules/seasons/{season_id}",
                params={"api_token": SPORTMONKS_KEY},
                timeout=self.timeout,
            )
            sch.raise_for_status()
            sj = sch.json() or {}
            sd = sj.get("data", [])
            if isinstance(sd, list):
                schedules = [row for row in sd if isinstance(row, dict)]
            else:
                schedules = []
        except Exception as exc:
            log.warning("sportmonks_schedules_err lid=%s season=%s err=%s", league_id, season_id, exc)
            _cache.set(cache_key, [])
            return []

        # Extract fixtures from schedules (stage -> rounds -> fixtures), shape-tolerant
        collected: List[Dict[str, Any]] = []

        def _as_list(x):
            if isinstance(x, list):
                return x
            if isinstance(x, dict):
                # common wrappers: {"data": [...]} or dict-of-dicts
                return x.get("data") or list(x.values())
            return []

        for row in schedules:
            # 1) Some comps might (rarely) expose fixtures at stage-level
            stage_level_fx = row.get("fixtures")
            for fx in _as_list(stage_level_fx):
                if isinstance(fx, dict):
                    collected.append(fx)

            # 2) Canonical: fixtures are under rounds[*].fixtures
            rounds = _as_list(row.get("rounds"))
            for rnd in rounds:
                rnd_fx = _as_list(rnd.get("fixtures") or rnd.get("games"))
                for fx in rnd_fx:
                    if isinstance(fx, dict):
                        collected.append(fx)

        # Filter fixtures by our window [date_from, date_to] using starting_at (YYYY-MM-DD)
        def _within(when: str) -> bool:
            ymd = str(when or "")[:10]
            return date_from <= ymd <= date_to

        data = [f for f in collected if _within(str(f.get("starting_at") or ""))]
        log.info("sportmonks_schedules_used lid=%s season=%s kept=%d", league_id, season_id, len(data))

        # ---- Map to feed items (defensive) ----
        items: List[Fixture] = []
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
            # Coerce participants to a list
            if isinstance(participants, dict):
                # common shapes: {"data": [...]} or plain id->object map
                participants = participants.get("data") or list(participants.values())
            if not isinstance(participants, list):
                participants = []

            scores = fx.get("scores") or []  # list of {participant_id, score, description/type}
            # Coerce scores to a list of dicts
            if isinstance(scores, dict):
                # if participant keyed or has nested totals, flatten best-effort
                scores = list(scores.values())
            if not isinstance(scores, list):
                scores = []
            score_by_pid: Dict[Any, Any] = {}
            try:
                for s in scores:
                    if not isinstance(s, dict):
                        continue
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
                if not isinstance(p, dict):
                    continue
                meta = (p.get("meta") or {})
                loc = str(meta.get("location", "")).lower()
                # Some responses nest the team under p['participant']; others keep team fields at top-level.
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

            # Heuristic fallback: if no meta.location, take first two as home/away
            if not home_raw and not away_raw and len(participants) >= 2:
                def _team_dict(pp: Any) -> Dict[str, Any]:
                    t = (pp.get("participant") or pp or {}) if isinstance(pp, dict) else {}
                    return {"id": t.get("id"), "name": t.get("name"), "score": None}

                home_raw = _team_dict(participants[0])
                away_raw = _team_dict(participants[1])

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

        log.info("sportmonks_fixtures_built code=%s lid=%s from=%s to=%s count=%d via_schedules=True",
                 competition_code, league_id, date_from, date_to, len(items))
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
