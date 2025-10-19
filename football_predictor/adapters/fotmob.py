from __future__ import annotations
from typing import List, Optional, Dict, Any, Tuple
import time
import threading
from datetime import datetime, timezone
import logging

from ..constants import fotmob_comp_id
from ..ports.fixtures import FixturesPort, Fixture
from ..ports.match_stats import MatchStatsPort, MatchStats
from ..ports.standings import StandingsPort, Standings
from ..ports.lineups import LineupsPort, Lineups
from ..ports.events import EventsPort, Events
from ..settings import FOTMOB_TIMEOUT_MS
from ..logging_utils import RateLimitedLogger
from ..constants import fotmob_comp_id
from ..fotmob_shared import to_iso_utc, season_from_iso, normalize_team_dict
from ..compat import patch_asyncio_for_py311
try:
    import soccerdata as sd
except Exception:
    sd = None

log = logging.getLogger(__name__)


# Simple in-process TTL cache to keep Replit happy (stub now; filled in later tasks)
class _TTLCache:
    def __init__(self):
        self._d: Dict[Tuple[Any, ...], Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Tuple[Any, ...], ttl_sec: float) -> Optional[Any]:
        now = time.time()
        with self._lock:
            v = self._d.get(key)
            if not v:
                return None
            ts, data = v
            if now - ts > ttl_sec:
                self._d.pop(key, None)
                return None
            return data

    def set(self, key: Tuple[Any, ...], value: Any) -> None:
        with self._lock:
            self._d[key] = (time.time(), value)


_cache = _TTLCache()

def _status_from_fotmob(
    raw_status: str | None, started: bool | None, finished: bool | None
) -> tuple[str, int | None]:
    """
    Normalize FotMob-ish status fields to our compact codes:
    - 'NS' (not started)
    - 'LIVE' (include minute if we can)
    - 'FT' (finished)
    Returns: (status, minute_or_None)
    """

    raw = (raw_status or "").strip().lower()
    if finished:
        return "FT", None
    if started and not finished:
        # Try to extract minute e.g. "72'" or "72"
        m = None
        for tok in (raw.replace("'", ""), raw.split("+")[0]):
            try:
                m = int("".join(ch for ch in tok if ch.isdigit()))
                break
            except Exception:
                pass
        return "LIVE", m
    return "NS", None
def _backoff_attempts():
    # yields small backoff (ms) with jitter. Keep tiny for Replit free tier.
    import random
    for base in (0.0, 0.15, 0.35):
        yield base + random.uniform(0, 0.15)


class FotMobAdapter(
    FixturesPort,
    MatchStatsPort,
    StandingsPort,
    LineupsPort,
    EventsPort,
):
    """
    Adapter implementing our ports using the fotmob-api library.
    NOTE: In this task, methods are safe stubs (returning empty shapes) to land structure.
          Actual provider calls will be implemented in T3/T4.
    """

    def __init__(self, timeout_ms: Optional[int] = None):
        self.timeout_s = (timeout_ms or FOTMOB_TIMEOUT_MS) / 1000.0
        # Defer import so the app doesn’t require the lib unless this adapter is used
        try:
            patch_asyncio_for_py311()
            from fotmob_api import FotMob  # type: ignore

            self._client_cls = FotMob
        except Exception as e:  # pragma: no cover - import failure path
            # Keep class constructible even if dep isn’t installed yet
            log.warning("fotmob_client_import_failed: %s", e)
            self._client_cls = None

    def _client(self):
        # Construct a new client per call for now (stateless); can pool later
        if self._client_cls is None:
            raise RuntimeError("FotMob client not available. Is 'fotmob-api' installed?")
        return self._client_cls(timeout=self.timeout_s)

    # -------- FixturesPort --------
    def list_competitions(self) -> List[dict]:
        t0 = time.perf_counter()
        # STUB: return empty list for now
        items: List[dict] = []
        log.info(
            "provider=fotmob op=list_competitions took_ms=%d result=ok count=%d",
            int((time.perf_counter() - t0) * 1000),
            len(items),
        )
        return items

    def get_fixtures(
        self, competition_code: str, start_iso: str, end_iso: str
    ) -> List[Fixture]:
        t0 = time.perf_counter()
        comp_id = fotmob_comp_id(competition_code)
        key = ("fixtures_mix", comp_id, start_iso, end_iso)
        cached = _cache.get(key, ttl_sec=60.0)
        if cached is not None:
            log.info(
                "provider=mix op=get_fixtures comp=%s window=%s..%s took_ms=%d result=cache count=%d",
                competition_code,
                start_iso,
                end_iso,
                int((time.perf_counter() - t0) * 1000),
                len(cached),
            )
            return cached

        try:
            sdt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
            edt = datetime.fromisoformat(end_iso.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        except Exception:
            log.warning("date_parse_failed start=%s end=%s", start_iso, end_iso)
            return []

        items: List[Fixture] = []

        comp_map_sd = {
            47: "ENG-Premier League",
            87: "ESP-La Liga",
            55: "ITA-Serie A",
            54: "GER-Bundesliga",
            53: "FRA-Ligue 1",
        }
        league_str = comp_map_sd.get(comp_id)

        if league_str and sd is not None:
            try:
                fm = sd.FotMob(leagues=[league_str], no_cache=True, no_store=True)
                df = fm.matches()
                for _, row in df.iterrows():
                    ko = row.get("Date")
                    if ko is None:
                        continue
                    if hasattr(ko, "to_pydatetime"):
                        ko_dt = ko.to_pydatetime().replace(tzinfo=timezone.utc)
                    else:
                        ko_dt = datetime.fromisoformat(str(ko)).replace(tzinfo=timezone.utc)
                    if not (sdt <= ko_dt <= edt):
                        continue

                    home = normalize_team_dict(
                        {
                            "id": row.get("HomeTeamId"),
                            "name": row.get("HomeTeam"),
                            "score": row.get("HomeGoals"),
                        }
                    )
                    away = normalize_team_dict(
                        {
                            "id": row.get("AwayTeamId"),
                            "name": row.get("AwayTeam"),
                            "score": row.get("AwayGoals"),
                        }
                    )
                    match_id = row.get("MatchId") or row.get("Id") or row.get("match_id")
                    if not match_id:
                        continue

                    items.append(
                        {
                            "match_id": str(match_id),
                            "competition": league_str,
                            "competition_code": competition_code,
                            "kickoff_iso": to_iso_utc(ko_dt),
                            "status": str(row.get("Status") or "").upper() or "NS",
                            "minute": None,
                            "home": home,
                            "away": away,
                        }
                    )
            except Exception as e:
                log.warning("soccerdata_fetch_failed league=%s error=%s", league_str, e)

        if not league_str:
            try:
                patch_asyncio_for_py311()
                from fotmob_api import FotmobAPI  # type: ignore

                api = FotmobAPI()
                season = season_from_iso(start_iso)
                raw = api.get_fixtures(id=comp_id, season=season)

                def iter_matches(r):
                    if not r:
                        return
                    if isinstance(r, list):
                        for it in r:
                            if isinstance(it, dict):
                                ms = (
                                    it.get("matches")
                                    or it.get("roundMatches")
                                    or it.get("fixtures")
                                )
                                if isinstance(ms, list):
                                    for m in ms:
                                        yield m
                                    continue
                            yield it
                    elif isinstance(r, dict):
                        ms = (
                            r.get("matches")
                            or r.get("roundMatches")
                            or r.get("fixtures")
                            or []
                        )
                        if isinstance(ms, list):
                            for m in ms:
                                yield m

                for m in iter_matches(raw):
                    mid = (
                        m.get("id")
                        or m.get("matchId")
                        or m.get("match_id")
                        or m.get("idMatch")
                    )
                    if not mid:
                        continue

                    ko_iso = None
                    if "time" in m:
                        try:
                            ts = float(m["time"])
                            ts = ts / (1000.0 if ts > 10_000_000_000 else 1.0)
                            ko_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                            ko_iso = to_iso_utc(ko_dt)
                        except Exception:
                            pass
                    if not ko_iso:
                        for k in ("date", "kickoff", "kickOffTime"):
                            v = m.get(k)
                            if v:
                                try:
                                    ko_dt = datetime.fromisoformat(
                                        str(v).replace("Z", "+00:00")
                                    ).astimezone(timezone.utc)
                                    ko_iso = to_iso_utc(ko_dt)
                                    break
                                except Exception:
                                    pass
                    if not ko_iso:
                        continue

                    ko_dt = datetime.fromisoformat(ko_iso.replace("Z", "+00:00"))
                    if not (sdt <= ko_dt <= edt):
                        continue

                    home = normalize_team_dict(m.get("home") or m.get("homeTeam") or {})
                    away = normalize_team_dict(m.get("away") or m.get("awayTeam") or {})

                    items.append(
                        {
                            "match_id": str(mid),
                            "competition": competition_code,
                            "competition_code": competition_code,
                            "kickoff_iso": ko_iso,
                            "status": (str(m.get("status") or m.get("statusText") or "").upper() or "NS"),
                            "minute": None,
                            "home": home,
                            "away": away,
                        }
                    )
            except Exception as e:
                log.warning(
                    "fotmobapi_fetch_failed comp_id=%s code=%s error=%s",
                    comp_id,
                    competition_code,
                    e,
                )

        try:
            items.sort(key=lambda it: it["kickoff_iso"])
        except Exception:
            pass
        _cache.set(key, items)
        log.info(
            "provider=mix op=get_fixtures comp=%s window=%s..%s took_ms=%d result=ok count=%d",
            competition_code,
            start_iso,
            end_iso,
            int((time.perf_counter() - t0) * 1000),
            len(items),
        )
        return items

    # -------- MatchStatsPort --------
    def get_match_stats(self, match_id: str) -> MatchStats:
        t0 = time.perf_counter()
        # STUB: minimal empty shape
        payload: MatchStats = {
            "match_id": str(match_id),
            "competition": "",
            "kickoff_iso": "",
            "status": "",
            "teams": [],
            "shots": [],
        }
        log.info(
            "provider=fotmob op=get_match_stats match=%s took_ms=%d result=ok",
            match_id,
            int((time.perf_counter() - t0) * 1000),
        )
        return payload

    # -------- StandingsPort --------
    def get_standings(self, competition_code: str, season: str) -> Standings:
        t0 = time.perf_counter()
        payload: Standings = {
            "competition_code": competition_code,
            "season": season,
            "table": [],
        }
        log.info(
            "provider=fotmob op=get_standings comp=%s season=%s took_ms=%d result=ok rows=%d",
            competition_code,
            season,
            int((time.perf_counter() - t0) * 1000),
            len(payload["table"]),
        )
        return payload

    # -------- LineupsPort --------
    def get_lineups(self, match_id: str) -> Lineups:
        t0 = time.perf_counter()
        payload: Lineups = {
            "match_id": str(match_id),
            "home": {
                "team_id": 0,
                "team_name": "",
                "formation": None,
                "starters": [],
                "bench": [],
            },
            "away": {
                "team_id": 0,
                "team_name": "",
                "formation": None,
                "starters": [],
                "bench": [],
            },
        }
        log.info(
            "provider=fotmob op=get_lineups match=%s took_ms=%d result=ok",
            match_id,
            int((time.perf_counter() - t0) * 1000),
        )
        return payload

    # -------- EventsPort --------
    def get_events(self, match_id: str) -> Events:
        t0 = time.perf_counter()
        payload: Events = {"match_id": str(match_id), "events": []}
        log.info(
            "provider=fotmob op=get_events match=%s took_ms=%d result=ok count=%d",
            match_id,
            int((time.perf_counter() - t0) * 1000),
            len(payload["events"]),
        )
        return payload
