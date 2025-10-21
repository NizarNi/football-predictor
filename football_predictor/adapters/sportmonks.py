from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import copy
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



def _fixture_includes() -> str:
    return "participants.team;venue;round;tvstations"


def _extract_team_logo(team: Dict[str, Any]) -> Optional[str]:
    if not isinstance(team, dict):
        return None
    logo = team.get("image_path")
    if isinstance(logo, str) and logo.strip():
        return logo
    return None


def _extract_round_name(fixture: Dict[str, Any]) -> Optional[str]:
    round_obj: Any = fixture.get("round")
    if isinstance(round_obj, dict) and "data" in round_obj:
        round_obj = round_obj.get("data")
    if isinstance(round_obj, dict):
        for key in ("name", "name_en", "name_translated"):
            value = round_obj.get(key)
            if isinstance(value, str) and value.strip():
                return value
    name = fixture.get("round_name") or fixture.get("round_name_en")
    if isinstance(name, str) and name.strip():
        return name
    return None


def _extract_venue(fixture: Dict[str, Any]) -> Optional[Dict[str, Optional[str]]]:
    venue_obj: Any = fixture.get("venue")
    if isinstance(venue_obj, dict) and "data" in venue_obj:
        venue_obj = venue_obj.get("data")
    if isinstance(venue_obj, dict):
        name = venue_obj.get("name") or venue_obj.get("name_en")
        city = (
            venue_obj.get("city")
            or venue_obj.get("city_name")
            or venue_obj.get("city_en")
            or venue_obj.get("city_translated")
        )
        if name or city:
            return {"name": name, "city": city}
    name = fixture.get("venue_name")
    city = fixture.get("venue_city")
    if name or city:
        return {"name": name, "city": city}
    return None


def _extract_tv_stations(fixture: Dict[str, Any]) -> List[str]:
    tv_raw: Any = fixture.get("tvstations") or fixture.get("tvStations")
    if isinstance(tv_raw, dict):
        tv_raw = tv_raw.get("data") or list(tv_raw.values())
    stations: List[str] = []
    if isinstance(tv_raw, list):
        for item in tv_raw:
            if isinstance(item, dict):
                name = item.get("name") or item.get("name_en")
            else:
                name = item
            if isinstance(name, str) and name.strip():
                stations.append(name)
    return stations


def _extract_referee(fixture: Dict[str, Any]) -> Optional[str]:
    referee_obj: Any = fixture.get("referee")
    if isinstance(referee_obj, dict) and "data" in referee_obj:
        referee_obj = referee_obj.get("data")
    if isinstance(referee_obj, dict):
        for key in ("fullname", "full_name", "name"):
            value = referee_obj.get(key)
            if isinstance(value, str) and value.strip():
                return value
    name = fixture.get("referee_name")
    if isinstance(name, str) and name.strip():
        return name
    return None


def _apply_logo_policy(items: List[Dict[str, Any]], include_logos: bool) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    for item in items:
        clone = copy.deepcopy(item)
        for key in ("home", "away"):
            side = clone.get(key)
            if isinstance(side, dict):
                if not include_logos:
                    side["logo"] = None
                else:
                    logo_val = side.get("logo")
                    if not isinstance(logo_val, str) or not logo_val.strip():
                        side["logo"] = None
        sanitized.append(clone)
    return sanitized


def _participant_team(participant: Dict[str, Any]) -> Dict[str, Any]:
    team = participant.get("team")
    if isinstance(team, dict) and "data" in team:
        team = team.get("data")
    if isinstance(team, dict) and team:
        return team
    base = participant.get("participant")
    if isinstance(base, dict) and base:
        return base
    return participant


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


FEED_CACHE_TTL_SEC = 600


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
            between = _sm_get(
                f"/fixtures/between/{start_ymd}/{end_ymd}",
                params={
                    "filters": f"fixtureLeagues:{league_id}",
                    "include": _fixture_includes(),
                },
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
        self.timeout = (timeout_ms or SPORTMONKS_TIMEOUT_MS) / 1000.0

    # -------- FixturesPort --------
    def get_fixtures(
        self,
        competition_code: str,
        start_iso: str,
        end_iso: str,
        include_logos: bool = True,
    ) -> List[Fixture]:
        league_id = sportmonks_league_id(competition_code)
        if not SPORTMONKS_KEY:
            log.warning("sportmonks_key_missing")
            return []
        if not league_id:
            log.info("sportmonks_league_unmapped_or_unavailable code=%s", competition_code)
            return []

        cache_key = ("sportmonks_fixtures", league_id, start_iso, end_iso)
        cached = _cache.get(cache_key, ttl=FEED_CACHE_TTL_SEC)
        if cached is not None:
            return _apply_logo_policy(cached, include_logos)

        date_from = _ymd(start_iso)
        date_to = _ymd(end_iso)
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
            if isinstance(participants, dict):
                participants = participants.get("data") or list(participants.values())
            if not isinstance(participants, list):
                participants = []

            scores = fx.get("scores") or []
            if isinstance(scores, dict):
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
                team_data = _participant_team(p)
                pid = team_data.get("id") or (p.get("participant") or {}).get("id")
                name = team_data.get("name") or (p.get("participant") or {}).get("name")

                p_score = None
                if isinstance(p.get("scores"), dict):
                    p_score = (p.get("scores") or {}).get("total")
                if p_score is None and pid in score_by_pid:
                    p_score = score_by_pid.get(pid)

                enriched = {
                    "id": pid,
                    "name": name,
                    "score": p_score,
                    "logo": _extract_team_logo(team_data) or _extract_team_logo(p),
                }

                if loc == "home":
                    home_raw = enriched
                elif loc == "away":
                    away_raw = enriched

            if not home_raw and not away_raw and len(participants) >= 2:

                def _team_dict(pp: Any) -> Dict[str, Any]:
                    t = _participant_team(pp) if isinstance(pp, dict) else {}
                    return {"id": t.get("id"), "name": t.get("name"), "score": None, "logo": _extract_team_logo(t)}

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

            home_logo = home_raw.get("logo")
            away_logo = away_raw.get("logo")
            if isinstance(home_logo, str) and home_logo.strip():
                home["logo"] = home_logo
            else:
                home["logo"] = home.get("logo") or None
            if isinstance(away_logo, str) and away_logo.strip():
                away["logo"] = away_logo
            else:
                away["logo"] = away.get("logo") or None

            status, minute = _map_status(fx.get("state") or {})
            round_name = _extract_round_name(fx)
            venue_info = _extract_venue(fx) or {"name": None, "city": None}
            tv_stations = _extract_tv_stations(fx)
            referee = _extract_referee(fx)

            try:
                fixture_int = int(fixture_id)
            except Exception:
                fixture_int = None

            league_val = fx.get("league_id") or league_id
            season_val = fx.get("season_id") or season_id

            item: Fixture = {
                "match_id": str(fixture_id),
                "competition": competition_code,
                "competition_code": competition_code,
                "kickoff_iso": kickoff_iso,
                "kickoff_utc": kickoff_iso,
                "status": status,
                "minute": minute,
                "home": home,
                "away": away,
                "league_id": int(league_val) if isinstance(league_val, int) else league_val,
                "season_id": int(season_val) if isinstance(season_val, int) else season_val,
                "round": round_name,
                "venue": venue_info,
            }
            if fixture_int is not None:
                item["fixture_id"] = fixture_int
            if tv_stations:
                item["tv_stations"] = tv_stations
            if referee:
                item["referee"] = referee

            items.append(item)

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
        return _apply_logo_policy(items, include_logos)

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
