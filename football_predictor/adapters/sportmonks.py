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
from .sportmonks_seasons import SeasonResolver, _sm_get

log = logging.getLogger(__name__)


SM_INCLUDES_STANDARD = [
    "participants",
    "participants.team",
    "participants.team.logo",
    "scores",
    "state",
]


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
resolver = SeasonResolver()


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


def _as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return x.get("data") or list(x.values())
    return []


def _log_invalid_season(league_id: int, sid: Any, source: str) -> None:
    try:
        log.info("sportmonks_season_invalid lid=%s sid=%s source=%s", league_id, sid, source)
    except Exception:
        pass


def _valid_season_id(sid: Any) -> Optional[int]:
    if isinstance(sid, int) and sid >= 10000:
        return sid
    return None


def season_id_for_window(league_id: int, start_ymd: str, end_ymd: str) -> Optional[int]:
    sid = resolver.get_for_date(league_id, start_ymd)
    valid = _valid_season_id(sid)
    if valid is not None:
        return valid
    if sid is not None and valid is None:
        _log_invalid_season(league_id, sid, "by_date")

    sid = resolver.get_current(league_id)
    valid = _valid_season_id(sid)
    if valid is not None:
        return valid
    if sid is not None and valid is None:
        _log_invalid_season(league_id, sid, "current")
    return None


def _log_season_resolution(league_id: int, season_id: Optional[int], start_ymd: str, end_ymd: str) -> None:
    msg = f"smonks_season_resolved lid={league_id} season={season_id} start={start_ymd} end={end_ymd}"
    log.info(msg)
    app_logger = globals().get("app_logger")
    if not app_logger:
        app = globals().get("app")
        if app is not None:
            app_logger = getattr(app, "logger", None)
    if app_logger and hasattr(app_logger, "info"):
        try:
            app_logger.info(msg)
        except Exception:
            pass


def fetch_league_window(
    league_id: int, start_ymd: str, end_ymd: str
) -> Tuple[List[Dict[str, Any]], Optional[int], bool]:
    fixtures: List[Dict[str, Any]] = []
    fallback_used = False
    season_id = season_id_for_window(league_id, start_ymd, end_ymd)
    _log_season_resolution(league_id, season_id, start_ymd, end_ymd)

    if season_id:
        try:
            params = {"include": ",".join(SM_INCLUDES_STANDARD)}
            try:
                data = _sm_get(f"/schedules/seasons/{season_id}", params=params)
            except Exception:
                data = _sm_get(f"/schedules/seasons/{season_id}")
            stages = _as_list(data.get("data"))
            for stage in stages:
                for rnd in _as_list(stage.get("rounds")):
                    for fx in _as_list(rnd.get("fixtures") or rnd.get("games")):
                        if isinstance(fx, dict):
                            when = str(fx.get("starting_at") or "")[:10]
                            if start_ymd <= when <= end_ymd:
                                fixtures.append(fx)
        except Exception as exc:
            log.warning(
                "sportmonks_schedules_err lid=%s season=%s err=%s",
                league_id,
                season_id,
                exc,
            )

    if not fixtures:
        fallback_used = True
        try:
            params = {
                "filters": f"fixtureLeagues:{league_id}",
                "include": ",".join(SM_INCLUDES_STANDARD),
            }
            try:
                between = _sm_get(
                    f"/fixtures/between/{start_ymd}/{end_ymd}",
                    params=params,
                )
            except Exception:
                between = _sm_get(
                    f"/fixtures/between/{start_ymd}/{end_ymd}",
                    params={"filters": f"fixtureLeagues:{league_id}"},
                )
            fixtures = [
                fx
                for fx in (between.get("data") or [])
                if isinstance(fx, dict)
                and start_ymd <= str(fx.get("starting_at") or "")[:10] <= end_ymd
            ]
        except Exception as exc:
            log.warning(
                "sportmonks_between_err lid=%s err=%s", league_id, exc
            )
            fixtures = []

    used_between = bool(fallback_used)
    try:
        msg = (
            f"sportmonks_schedules_used lid={league_id} season={season_id} "
            f"kept={len(fixtures)} fallback={used_between}"
        )
        log.info(msg)
        app_logger = globals().get("app_logger")
        if not app_logger:
            app = globals().get("app")
            if app is not None:
                app_logger = getattr(app, "logger", None)
        if app_logger and hasattr(app_logger, "info"):
            app_logger.info(msg)
    except Exception:
        pass
    return fixtures, season_id, fallback_used


class SportmonksAdapter(FixturesPort, LineupsPort, StandingsPort):
    def __init__(self, timeout_ms: Optional[int] = None) -> None:
        self.key = SPORTMONKS_KEY or ""
        self._timeout = (timeout_ms or SPORTMONKS_TIMEOUT_MS) / 1000.0
        self.timeout = self._timeout
        self._session = _session()

    def _get_logo_from_team_node(self, team: dict) -> str | None:
        # Support both historical and current shapes
        # preferred (v3 relation):
        path = ((((team or {}).get("logo") or {}).get("data") or {}).get("path"))
        if path:
            return path
        # common fallback:
        return (team or {}).get("image_path")

    def _get_logo_from_participant(self, p: dict) -> str | None:
        team = ((p or {}).get("team") or {}).get("data") or {}
        return self._get_logo_from_team_node(team)

    def _fetch_team_logo(self, team_id: int) -> str | None:
        if not self.key:
            return None
        url = f"{SPORTMONKS_BASE}/teams/{team_id}"
        params = {"api_token": self.key, "include": "logo"}
        try:
            r = self._session.get(url, params=params, timeout=self._timeout)
        except Exception:
            return None
        if r.status_code != 200:
            return None
        try:
            data = (r.json() or {}).get("data") or {}
        except Exception:
            return None
        return self._get_logo_from_team_node(data)

    # -------- FixturesPort --------
    def get_fixtures(self, competition_code: str, start_iso: str, end_iso: str) -> List[Fixture]:
        league_id = sportmonks_league_id(competition_code)
        if not self.key:
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
        data, season_id, fallback_used = fetch_league_window(league_id, date_from, date_to)

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
            home_p = None
            away_p = None

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
                    home_p = p
                elif loc == "away":
                    away_raw = enriched
                    away_p = p

            # Heuristic fallback: if no meta.location, take first two as home/away
            if not home_raw and not away_raw and len(participants) >= 2:
                def _team_dict(pp: Any) -> Dict[str, Any]:
                    t = (pp.get("participant") or pp or {}) if isinstance(pp, dict) else {}
                    return {"id": t.get("id"), "name": t.get("name"), "score": None}

                first = participants[0] if isinstance(participants[0], dict) else {}
                second = participants[1] if isinstance(participants[1], dict) else {}
                home_raw = _team_dict(first)
                away_raw = _team_dict(second)
                home_p = first if isinstance(first, dict) else None
                away_p = second if isinstance(second, dict) else None
            else:
                if not home_raw:
                    for candidate in participants:
                        if isinstance(candidate, dict):
                            t = (candidate.get("participant") or candidate or {})
                            home_raw = {
                                "id": t.get("id"),
                                "name": t.get("name"),
                                "score": None,
                            }
                            home_p = candidate
                            break
                if not away_raw:
                    for candidate in reversed(participants):
                        if isinstance(candidate, dict):
                            t = (candidate.get("participant") or candidate or {})
                            away_raw = {
                                "id": t.get("id"),
                                "name": t.get("name"),
                                "score": None,
                            }
                            away_p = candidate
                            break

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

            fixture = {
                "match_id": str(fixture_id),
                "competition": competition_code,
                "competition_code": competition_code,
                "kickoff_iso": kickoff_iso,
                "status": status,
                "minute": minute,
                "home": home,
                "away": away,
            }

            home_team = ((home_p or {}).get("team") or {}).get("data") or {}
            away_team = ((away_p or {}).get("team") or {}).get("data") or {}

            home_logo = self._get_logo_from_participant(home_p or {})
            away_logo = self._get_logo_from_participant(away_p or {})

            home_id = home_team.get("id") if isinstance(home_team, dict) else None
            away_id = away_team.get("id") if isinstance(away_team, dict) else None

            if not isinstance(home_id, int):
                maybe_home = home.get("id")
                if isinstance(maybe_home, int):
                    home_id = maybe_home
            if not isinstance(away_id, int):
                maybe_away = away.get("id")
                if isinstance(maybe_away, int):
                    away_id = maybe_away

            if not home_logo and home_id:
                fetched = self._fetch_team_logo(home_id)
                home_logo = fetched or home_logo
            if not away_logo and away_id:
                fetched = self._fetch_team_logo(away_id)
                away_logo = fetched or away_logo

            if home_logo:
                fixture["home"]["logo"] = home_logo
            if away_logo:
                fixture["away"]["logo"] = away_logo

            fixture["home"]["logo_url"] = home_logo or fixture["home"].get("logo")
            fixture["away"]["logo_url"] = away_logo or fixture["away"].get("logo")

            items.append(fixture)

        try:
            items.sort(key=lambda item: item["kickoff_iso"])
        except Exception:
            pass

        log.info(
            "sportmonks_fixtures_built code=%s lid=%s from=%s to=%s count=%d via_schedules=%s",
            competition_code,
            league_id,
            date_from,
            date_to,
            len(items),
            not fallback_used,
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
