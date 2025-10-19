from __future__ import annotations
from typing import List, Optional, Dict, Any, Tuple
import time
import threading
from datetime import datetime, timezone

from ..ports.fixtures import FixturesPort, Fixture
from ..ports.match_stats import MatchStatsPort, MatchStats
from ..ports.standings import StandingsPort, Standings
from ..ports.lineups import LineupsPort, Lineups
from ..ports.events import EventsPort, Events
from ..settings import FOTMOB_TIMEOUT_MS
from ..logging_utils import RateLimitedLogger
from ..constants import fotmob_comp_id

log = RateLimitedLogger(__name__)


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


ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _to_iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime(ISO_FMT)


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


def _norm_team(t: dict) -> dict:
    # Accept common shapes, be defensive
    name = t.get("name") or t.get("shortName") or t.get("teamName") or ""
    tid = t.get("id") or t.get("teamId") or t.get("idTeam") or 0
    score = t.get("score")
    try:
        score = int(score) if score is not None else None
    except Exception:
        score = None
    return {"id": int(tid) if tid else 0, "name": str(name), "score": score}


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
        key = ("fixtures", comp_id, start_iso, end_iso)
        cached = _cache.get(key, ttl_sec=60.0)
        if cached is not None:
            log.info(
                "provider=fotmob op=get_fixtures comp=%s window=%s..%s took_ms=%d result=cache count=%d",
                competition_code,
                start_iso,
                end_iso,
                int((time.perf_counter() - t0) * 1000),
                len(cached),
            )
            return cached

        try:
            start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        except Exception:
            start_dt = datetime.strptime(start_iso[:10], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            end_dt = datetime.strptime(end_iso[:10], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )

        date_from = start_dt.strftime("%Y-%m-%d")
        date_to = end_dt.strftime("%Y-%m-%d")

        last_err: Optional[Exception] = None
        for backoff in _backoff_attempts():
            try:
                client = self._client()
                raw = client.get_fixtures(
                    competition_id=comp_id, date_from=date_from, date_to=date_to
                )
                break
            except Exception as e:
                last_err = e
                time.sleep(backoff)
        else:
            log.warning(
                "provider=fotmob op=get_fixtures comp=%s window=%s..%s error=%s",
                competition_code,
                start_iso,
                end_iso,
                last_err,
            )
            return []

        items: List[Fixture] = []
        try:
            for m in (raw or []):
                match_id = (
                    m.get("id")
                    or m.get("matchId")
                    or m.get("fixtureId")
                    or m.get("matchID")
                )
                league_name = (
                    m.get("leagueName")
                    or m.get("competition")
                    or m.get("tournamentName")
                    or competition_code
                )
                kickoff_raw = m.get("date") or m.get("kickoff") or m.get("time")
                if isinstance(kickoff_raw, (int, float)):
                    kickoff_iso = _to_iso_utc(
                        datetime.fromtimestamp(float(kickoff_raw), tz=timezone.utc)
                    )
                else:
                    try:
                        kickoff_iso = _to_iso_utc(
                            datetime.fromisoformat(
                                str(kickoff_raw).replace("Z", "+00:00")
                            )
                        )
                    except Exception:
                        try:
                            kickoff_iso = _to_iso_utc(
                                datetime.strptime(
                                    str(kickoff_raw)[:10], "%Y-%m-%d"
                                ).replace(tzinfo=timezone.utc)
                            )
                        except Exception:
                            kickoff_iso = _to_iso_utc(start_dt)

                started = m.get("started") or m.get("isLive") or False
                finished = m.get("finished") or m.get("isFinished") or False
                raw_status = (
                    m.get("status") or m.get("statusText") or m.get("liveStatus")
                )
                status, minute = _status_from_fotmob(
                    raw_status, bool(started), bool(finished)
                )

                home = _norm_team(m.get("home") or m.get("homeTeam") or {})
                away = _norm_team(m.get("away") or m.get("awayTeam") or {})

                if not match_id:
                    continue

                items.append(
                    {
                        "match_id": str(match_id),
                        "competition": str(league_name),
                        "competition_code": competition_code,
                        "kickoff_iso": kickoff_iso,
                        "status": status,
                        "minute": minute,
                        "home": home,
                        "away": away,
                    }
                )
        except Exception as e:
            log.warning(
                "provider=fotmob op=get_fixtures normalize_failed comp=%s error=%s",
                competition_code,
                e,
            )
            items = []

        try:
            items.sort(key=lambda it: it["kickoff_iso"])
        except Exception:
            pass

        _cache.set(key, items)
        log.info(
            "provider=fotmob op=get_fixtures comp=%s window=%s..%s took_ms=%d result=ok count=%d",
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
