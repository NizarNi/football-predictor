from __future__ import annotations
from typing import List, Optional, Dict, Any, Tuple
import time
import threading

from ..ports.fixtures import FixturesPort, Fixture
from ..ports.match_stats import MatchStatsPort, MatchStats
from ..ports.standings import StandingsPort, Standings
from ..ports.lineups import LineupsPort, Lineups
from ..ports.events import EventsPort, Events
from ..settings import FOTMOB_TIMEOUT_MS
from ..logging_utils import RateLimitedLogger

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
        # STUB: empty list; normalization will be added in T3.1
        result: List[Fixture] = []
        log.info(
            "provider=fotmob op=get_fixtures comp=%s window=%s..%s took_ms=%d result=ok count=%d",
            competition_code,
            start_iso,
            end_iso,
            int((time.perf_counter() - t0) * 1000),
            len(result),
        )
        return result

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
