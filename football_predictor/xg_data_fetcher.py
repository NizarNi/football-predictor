"""
xG Data Fetcher Module
Fetches Expected Goals (xG) statistics from FBref using soccerdata library
"""
from contextvars import ContextVar
from datetime import datetime, timedelta
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, Optional, Tuple, List
from dataclasses import dataclass

import json
import os
import re
import threading
import time

import pandas as pd
import requests
import soccerdata as sd

from .app_utils import AdaptiveTimeoutController
from .utils import create_retry_session, get_xg_season
from .config import API_MAX_RETRIES, API_TIMEOUT, setup_logger
from .errors import APIError
from .constants import (
    CAREER_XG_CACHE_TTL,
    LEAGUE_MAPPING,
    MATCH_LOGS_CACHE_TTL,
)
from .name_resolver import resolve_team_name, get_all_aliases_for

# ----------------------------------------------------------------------
# Paths, TTLs, logger
# ----------------------------------------------------------------------

CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "processed_data", "xg_cache")
)
LEGACY_CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "processed_data", "xg_cache")
)
SOFT_TTL_SECONDS = 6 * 3600
HARD_TTL_SECONDS = 24 * 3600
INMEM_TTL_SECONDS = 60

DOMESTIC_MAPPING_FALLBACK_MESSAGE = (
    "FBref mapping refresh in progress for this club. Please try again shortly while we sync the aliases."
)

SUPPORTED_DOMESTIC = ["PL", "PD", "SA", "BL1", "FL1"]


def _infer_domestic_league_for_both(canonical_home: str, canonical_away: str) -> Optional[str]:
    for code in SUPPORTED_DOMESTIC:
        table = fetch_league_xg_stats(code, cache_only=True)
        if not table:
            continue

        def _has_team(name: str) -> bool:
            if name in table:
                return True
            for alias in get_all_aliases_for(name):
                if alias in table:
                    return True
            # last-chance: light case-insensitive partial
            n = name.lower()
            return any(n in k.lower() or k.lower() in n for k in table.keys())

        if _has_team(canonical_home) and _has_team(canonical_away):
            return code
    return None


# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)

logger = setup_logger(__name__)
logger.info("xg_data_fetcher: using cache dir at %s", CACHE_DIR)
if os.path.exists(LEGACY_CACHE_DIR) and LEGACY_CACHE_DIR != CACHE_DIR:
    logger.warning("xg_data_fetcher: ignoring legacy cache dir at %s", LEGACY_CACHE_DIR)

# Background worker pool (league + logs refresh)
_executor = ThreadPoolExecutor(max_workers=4)

# ----------------------------------------------------------------------
# Debounce registry (T35e): bounded backoff per (league, team) and per league
# ----------------------------------------------------------------------
@dataclass
class DebounceState:
    last_try_s: float = 0.0
    backoff_s: float = 0.0   # increases on failure, resets on success
    attempts: int = 0


_DEBOUNCE: Dict[Tuple[str, Optional[str]], DebounceState] = {}


def _should_debounce(key: Tuple[str, Optional[str]], floor: float, ceil: float) -> bool:
    st = _DEBOUNCE.get(key)
    if not st:
        return False
    now = time.monotonic()
    wait = max(floor, min(ceil, st.backoff_s or floor))
    return (now - st.last_try_s) < wait


def _mark_attempt(key: Tuple[str, Optional[str]], ok: bool, floor: float, ceil: float) -> None:
    st = _DEBOUNCE.get(key) or DebounceState()
    st.last_try_s = time.monotonic()
    if ok:
        st.backoff_s = 0.0
        st.attempts = 0
    else:
        # bounded exponential backoff
        base = st.backoff_s * 2 if st.backoff_s else floor
        st.backoff_s = min(ceil, base)
        st.attempts += 1
    _DEBOUNCE[key] = st

# ----------------------------------------------------------------------
# Debounce state (T35d): per (league, team) cooldown + single stacktrace window
# ----------------------------------------------------------------------
_refresh_attempt_lock = threading.Lock()
_last_refresh_attempt: Dict[Tuple[str, str], float] = {}
REFRESH_COOLDOWN_S = 120

def _clear_refresh_attempt(league_code: str, canonical_team: str) -> None:
    with _refresh_attempt_lock:
        _last_refresh_attempt.pop((league_code, canonical_team), None)

_stacktrace_guard_lock = threading.Lock()
_last_stacktrace_log: Dict[Tuple[str, str], float] = {}

# Background refresh guard (single-flight per (league, season) for league tables)
_background_refreshes = set()

# Adaptive timeout controller for FBref calls
adaptive_timeout = AdaptiveTimeoutController(base_timeout=API_TIMEOUT, max_timeout=30)

# ----------------------------------------------------------------------
# Request-scoped memo (prevents duplicate work within one HTTP request)
# ----------------------------------------------------------------------

_request_memo_id: ContextVar[Optional[str]] = ContextVar("xg_request_memo_id", default=None)
_request_memo_store: Dict[str, Dict[Tuple[str, str, int], Any]] = {}
_request_memo_lock = threading.Lock()

_league_alias_summary: ContextVar[Optional[List[Tuple[str, str]]]] = ContextVar(
    "xg_league_alias_summary", default=None
)

def set_request_memo_id(request_id: Optional[str]) -> None:
    """Register the active request memo identifier for match log reuse."""
    _request_memo_id.set(request_id)
    if request_id is None:
        return
    with _request_memo_lock:
        _request_memo_store.setdefault(request_id, {})

def clear_request_memo_id() -> None:
    """Clear memoized match logs for the current request."""
    request_id = _request_memo_id.get()
    if request_id:
        with _request_memo_lock:
            _request_memo_store.pop(request_id, None)
    _request_memo_id.set(None)

def get_current_request_memo_id() -> Optional[str]:
    """Return the memo identifier associated with the current request (if any)."""
    return _request_memo_id.get()

def _get_request_memo_bucket(request_id: Optional[str]):
    if not request_id:
        return None
    with _request_memo_lock:
        return _request_memo_store.setdefault(request_id, {})

# ----------------------------------------------------------------------
# HTTP session with retries/backoff for FBref (soccerdata)
# ----------------------------------------------------------------------

STATUS_FORCELIST = (429, 500, 502, 503, 504)
BACKOFF_FACTOR = 0.5

_xg_session = create_retry_session(
    max_retries=API_MAX_RETRIES,
    backoff_factor=BACKOFF_FACTOR,
    status_forcelist=STATUS_FORCELIST,
)

# ----------------------------------------------------------------------
# In-memory cache for match logs (TTL 60s) + per-team fetch locks
# ----------------------------------------------------------------------

MATCH_LOGS_CACHE: Dict[Tuple[str, str, int], Tuple[float, Any]] = {}
_MATCH_LOGS_CACHE_LOCK = threading.Lock()

# ----------------------------------------------------------------------
# Rolling xG utilities (request partial-window warnings)
# ----------------------------------------------------------------------

_PARTIAL_WINDOW_WARNINGS: set[tuple[str, str, int]] = set()

_MATCH_LOGS_FETCH_LOCKS: Dict[Tuple[str, str, int], threading.Lock] = {}
_MATCH_LOGS_FETCH_LOCKS_LOCK = threading.Lock()

def _match_logs_cache_prune_locked(now: Optional[float] = None) -> None:
    if now is None:
        now = time.time()
    expired_keys = [key for key, (expires_at, _data) in MATCH_LOGS_CACHE.items() if expires_at <= now]
    for key in expired_keys:
        MATCH_LOGS_CACHE.pop(key, None)

def _match_logs_cache_get(key: Tuple[str, str, int]) -> Optional[Any]:
    now = time.time()
    with _MATCH_LOGS_CACHE_LOCK:
        entry = MATCH_LOGS_CACHE.get(key)
        if not entry:
            return None
        expires_at, data = entry
        if expires_at <= now:
            MATCH_LOGS_CACHE.pop(key, None)
            return None
        return data

def _match_logs_cache_set(key: Tuple[str, str, int], data: Any) -> None:
    expires_at = time.time() + INMEM_TTL_SECONDS
    with _MATCH_LOGS_CACHE_LOCK:
        MATCH_LOGS_CACHE[key] = (expires_at, data)
        if len(MATCH_LOGS_CACHE) > 256:
            _match_logs_cache_prune_locked(now=time.time())

def _get_match_logs_fetch_lock(key: Tuple[str, str, int]) -> threading.Lock:
    with _MATCH_LOGS_FETCH_LOCKS_LOCK:
        lock = _MATCH_LOGS_FETCH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _MATCH_LOGS_FETCH_LOCKS[key] = lock
        return lock

# ----------------------------------------------------------------------
# Disk cache helpers for team match logs
# ----------------------------------------------------------------------

def _canonicalize_team_for_cache(team_name: str) -> str:
    """Make a file-safe slug using the unified resolver (FBref provider)."""
    canonical = resolve_team_name(team_name or "team", provider="fbref")
    slug = canonical.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug or "team"

def _team_match_logs_cache_key(league_code: str, season: int, team_name: str) -> str:
    team_slug = _canonicalize_team_for_cache(team_name)
    return f"matchlogs_{league_code.lower()}_{season}_{team_slug}"

def _team_match_logs_cache_path(league_code: str, season: int, team_name: str) -> str:
    cache_key = _team_match_logs_cache_key(league_code, season, team_name)
    return os.path.join(CACHE_DIR, f"{cache_key}.json")

def _load_team_match_logs_from_disk(
    league_code: str, season: int, team_name: str
) -> Optional[Any]:
    cache_path = _team_match_logs_cache_path(league_code, season, team_name)
    if not os.path.exists(cache_path):
        return None

    try:
        age_seconds = time.time() - os.path.getmtime(cache_path)
        if age_seconds > MATCH_LOGS_CACHE_TTL:
            return None

        with open(cache_path, "r", encoding="utf-8") as cache_file:
            return json.load(cache_file)
    except json.JSONDecodeError as exc:
        logger.warning(
            "xg_data_fetcher: invalid JSON in match logs cache for %s (%s %s): %s",
            team_name,
            league_code,
            season,
            exc,
        )
        try:
            os.remove(cache_path)
        except OSError:
            logger.warning(
                "xg_data_fetcher: unable to delete corrupt cache file %s", cache_path
            )
        return None
    except Exception:
        logger.exception(
            "xg_data_fetcher: failed to load team match logs cache for %s (%s %s)",
            team_name,
            league_code,
            season,
        )
        return None


def _json_safe(value: Any) -> Any:
    """Convert values that are not JSON serializable into safe representations."""

    if isinstance(value, (datetime, pd.Timestamp)):
        try:
            if hasattr(pd, "isna") and pd.isna(value):  # type: ignore[attr-defined]
                return None
        except Exception:
            if value is None:
                return None
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value

def _save_team_match_logs_to_disk(
    league_code: str, season: int, team_name: str, payload: Any
) -> None:
    cache_path = _team_match_logs_cache_path(league_code, season, team_name)
    try:
        json_payload = _json_safe(payload)
        with open(cache_path, "w", encoding="utf-8") as cache_file:
            json.dump(json_payload, cache_file)
    except Exception:
        logger.exception(
            "xg_data_fetcher: failed to persist team match logs cache for %s (%s %s)",
            team_name, league_code, season,
        )

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _resolve_fbref_team_name(raw_name: str, context: str) -> str:
    canonical = resolve_team_name(raw_name, provider="fbref")
    if raw_name and canonical != raw_name:
        if context == "league_xg_fetch":
            logger.debug(
                "league_xg_fetch: resolved '%s' → '%s' for FBref", raw_name, canonical
            )
            bucket = _league_alias_summary.get()
            if bucket is not None:
                bucket.append((raw_name, canonical))
        else:
            logger.info("🔁 %s: resolved '%s' → '%s' for FBref", context, raw_name, canonical)
    return canonical

def _configure_fbref_client(fbref_client):
    """Attach the retry session to a soccerdata FBref client when possible."""
    timeout = adaptive_timeout.get_timeout()

    for attr in ("session", "_session"):
        if hasattr(fbref_client, attr):
            current = getattr(fbref_client, attr)
            if isinstance(current, requests.Session):
                setattr(fbref_client, attr, _xg_session)

    if hasattr(fbref_client, "timeout"):
        try:
            setattr(fbref_client, "timeout", timeout)
        except Exception:
            pass

    return fbref_client

def _safe_soccerdata_call(func, context: str, *args, **kwargs):
    """Execute a soccerdata call and wrap network errors with adaptive timeout updates."""
    for attempt in range(3):
        timeout = adaptive_timeout.get_timeout()
        bound_client = getattr(func, "__self__", None)
        if bound_client is not None and hasattr(bound_client, "timeout"):
            try:
                setattr(bound_client, "timeout", timeout)
            except Exception:
                pass

        try:
            result = func(*args, **kwargs)
            adaptive_timeout.record_success()
            return result
        except requests.exceptions.Timeout as exc:
            adaptive_timeout.record_failure()
            logger.warning("[Resilience] API timeout or network issue: %s", exc)
            logger.error("❌ %s timed out", context)
            if attempt == 2:
                raise APIError("FBRefAPI", "TIMEOUT", "The FBRef API did not respond in time.") from exc
        except requests.exceptions.ConnectionError as exc:
            adaptive_timeout.record_failure()
            error_msg = str(exc)
            logger.warning("[Resilience] API timeout or network issue: %s", exc)
            logger.error("❌ %s: %s", context, error_msg)
            if attempt == 2:
                raise APIError(
                    "FBRefAPI", "NETWORK_ERROR", "A network error occurred.", error_msg
                ) from exc
        except requests.exceptions.RequestException as exc:
            adaptive_timeout.record_failure()
            error_msg = str(exc)
            logger.warning("[Resilience] API request failure detected: %s", exc)
            logger.error("❌ %s: %s", context, error_msg)
            if attempt == 2:
                raise APIError(
                    "FBRefAPI", "NETWORK_ERROR", "A network error occurred.", error_msg
                ) from exc
        except ValueError as exc:
            error_msg = str(exc)
            logger.error("❌ %s parse error: %s", context, error_msg)
            raise APIError(
                "FBRefAPI", "PARSE_ERROR", "Failed to parse API response.", error_msg
            ) from exc

        if attempt < 2:
            backoff = 0.8 * (2 ** attempt)
            time.sleep(backoff)

# ----------------------------------------------------------------------
# League xG cache (league-wide) with stale-while-revalidate
# ----------------------------------------------------------------------

_LEAGUE_MEM_CACHE: Dict[Tuple[str, int], Tuple[float, Dict[str, Any]]] = {}
_LEAGUE_MEM_CACHE_LOCK = threading.Lock()


def _get_from_mem_cache(league_code: str, season: int) -> Tuple[Optional[Dict[str, Any]], Optional[float]]:
    key = (league_code, season)
    with _LEAGUE_MEM_CACHE_LOCK:
        entry = _LEAGUE_MEM_CACHE.get(key)
    if not entry:
        return None, None
    stored_at, data = entry
    age = time.time() - stored_at
    return data, age


def _set_mem_cache(league_code: str, season: int, data: Dict[str, Any]) -> None:
    key = (league_code, season)
    with _LEAGUE_MEM_CACHE_LOCK:
        _LEAGUE_MEM_CACHE[key] = (time.time(), data)
    # Clear any per-league debounce/stacktrace guards when we successfully refreshed
    with _refresh_attempt_lock:
        stale_keys = [k for k in _last_refresh_attempt if k[0] == league_code]
        for entry in stale_keys:
            _last_refresh_attempt.pop(entry, None)
    with _stacktrace_guard_lock:
        stale_logs = [k for k in _last_stacktrace_log if k[0] == league_code]
        for entry in stale_logs:
            _last_stacktrace_log.pop(entry, None)
    # Also reset adaptive debounce window for this league
    try:
        deb_key = (league_code, None)
        if deb_key in _DEBOUNCE:
            _DEBOUNCE.pop(deb_key, None)
    except Exception:
        pass


def _is_stale(age_seconds: Optional[float]) -> bool:
    if age_seconds is None:
        return False
    return age_seconds >= SOFT_TTL_SECONDS


def _is_hard_expired(age_seconds: Optional[float]) -> bool:
    if age_seconds is None:
        return False
    return age_seconds >= HARD_TTL_SECONDS


def _refresh_league_async(league_code: str, season: int) -> None:
    # T35e: per-league backoff window (60s → 10m)
    deb_key = (league_code, None)
    if _should_debounce(deb_key, floor=60.0, ceil=600.0):
        logger.info("⏳ league-refresh debounced for %s", league_code)
        return

    refresh_key = (league_code, season)
    if refresh_key in _background_refreshes:
        return

    _background_refreshes.add(refresh_key)

    def _task():
        try:
            _fetch_and_cache_league_stats_now(league_code, season)
            _mark_attempt(deb_key, ok=True, floor=60.0, ceil=600.0)
            logger.info("✅ league-refresh ok for %s", league_code)
        except Exception as exc:  # best-effort
            _mark_attempt(deb_key, ok=False, floor=60.0, ceil=600.0)
            logger.warning(
                "xg_data_fetcher: background refresh failed for %s (%s): %s",
                league_code,
                season,
                exc,
            )
        finally:
            _background_refreshes.discard(refresh_key)

    _executor.submit(_task)


def _refresh_logs_async(
    league_code: str, canonical_team: str, season: Optional[int] = None
) -> None:
    # T35d fixed cooldown (120s) — keep as a first guard
    now = time.monotonic()
    key_cool = (league_code, canonical_team)
    with _refresh_attempt_lock:
        last = _last_refresh_attempt.get(key_cool, 0.0)
        if now - last < REFRESH_COOLDOWN_S:
            return
        _last_refresh_attempt[key_cool] = now

    # T35e adaptive backoff (90s → 15m)
    deb_key = (league_code, canonical_team)
    if _should_debounce(deb_key, floor=90.0, ceil=900.0):
        logger.info("⏳ logs-refresh debounced for %s/%s", league_code, canonical_team)
        return

    def _logs_task():
        try:
            _ensure_team_logs_fresh(league_code, canonical_team, season)
            _mark_attempt(deb_key, ok=True, floor=90.0, ceil=900.0)
            logger.info("✅ logs-refresh ok for %s/%s", league_code, canonical_team)
        except Exception as exc:
            _mark_attempt(deb_key, ok=False, floor=90.0, ceil=900.0)
            # _ensure_team_logs_fresh already swallows/logs details per T35d
            logger.warning("⚠️ logs-refresh failed for %s/%s: %s", league_code, canonical_team, exc)

    _executor.submit(_logs_task)

def get_cache_key(league_code, season):
    """Generate cache key for xG data"""
    return f"{league_code}_{season}"

def load_from_cache(cache_key):
    """Load xG data from cache with backward compatibility"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")

    if not os.path.exists(cache_file):
        return None

    try:
        with open(cache_file, 'r') as f:
            data = json.load(f)

        # Backward compatibility: migrate old xg_overperformance to scoring_clinicality
        for team_name, team_data in data.items():
            if 'xg_overperformance' in team_data and 'scoring_clinicality' not in team_data:
                team_data['scoring_clinicality'] = team_data['xg_overperformance']
                logger.info("🔄 Migrated %s: xg_overperformance → scoring_clinicality", team_name)

        # Canonicalize keys
        canonicalized_data = {}
        for team_name, team_data in data.items():
            canonical_name = resolve_team_name(team_name, provider="fbref")
            canonicalized_data[canonical_name] = team_data
        data = canonicalized_data

        age_seconds = time.time() - os.path.getmtime(cache_file)
        return data, age_seconds
    except Exception:
        logger.exception("Error loading cache")
        return None

def save_to_cache(cache_key, data):
    """Save xG data to cache"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    try:
        with open(cache_file, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        logger.exception("Error saving cache")

# ----------------------------------------------------------------------
# Career xG (last ~5 seasons) with in-process memo
# ----------------------------------------------------------------------

CAREER_XG_CACHE: Dict[str, Dict[str, Any]] = {}

def fetch_career_xg_stats(team_name, league_code):
    """
    Fetch recent historical xG statistics for a team (last 5 seasons)
    """
    if league_code not in LEAGUE_MAPPING:
        logger.warning("⚠️  League %s not supported for career xG", league_code)
        return None

    canonical_team_name = _resolve_fbref_team_name(team_name, "career_xg")

    # Check memo cache first
    cache_key = f"{canonical_team_name}_{league_code}_career"
    legacy_cache_key = f"{team_name}_{league_code}_career"
    current_time = datetime.now().timestamp()

    if cache_key in CAREER_XG_CACHE:
        cached_data = CAREER_XG_CACHE[cache_key]
        cache_age = current_time - cached_data['timestamp']
        if cache_age < CAREER_XG_CACHE_TTL:
            logger.info("✅ Using cached career xG for %s (age: %.1f days)", team_name, cache_age / 86400)
            return cached_data['data']

    if legacy_cache_key in CAREER_XG_CACHE:
        cached_data = CAREER_XG_CACHE.pop(legacy_cache_key)
        CAREER_XG_CACHE[cache_key] = cached_data
        cache_age = current_time - cached_data['timestamp']
        if cache_age < CAREER_XG_CACHE_TTL:
            logger.info("✅ Using cached career xG for %s (age: %.1f days)", canonical_team_name, cache_age / 86400)
            return cached_data['data']

    league_name = LEAGUE_MAPPING[league_code]
    lookup_name = canonical_team_name

    seasons_data = []
    current_season = get_xg_season()
    start_season = max(2021, current_season - 4)

    logger.info("📊 Fetching career xG for %s in %s (%d-%d)...",
                team_name, league_name, start_season, current_season)

    for season in range(start_season, current_season + 1):
        try:
            fbref = _configure_fbref_client(sd.FBref(leagues=league_name, seasons=season))
            stats_df = _safe_soccerdata_call(
                fbref.read_team_season_stats,
                f"FBref season stats ({league_code} {season})",
                stat_type='standard',
            )

            # Find team in stats
            team_stats = None
            for idx, row in stats_df.iterrows():
                # Extract team name from MultiIndex
                if isinstance(idx, tuple):
                    team_in_row = idx[-1]
                else:
                    team_in_row = str(idx)

                if resolve_team_name(team_in_row, provider="fbref") == lookup_name:
                    team_stats = row
                    break

            if team_stats is not None:
                xg_for = 0
                xga = 0
                games = 0

                # xG For
                if ('Expected', 'xG') in team_stats.index:
                    xg_for = float(team_stats[('Expected', 'xG')]) if pd.notna(team_stats[('Expected', 'xG')]) else 0
                elif 'xG' in team_stats.index:
                    xg_for = float(team_stats['xG']) if pd.notna(team_stats['xG']) else 0

                # xGA
                if ('Expected', 'xGA') in team_stats.index:
                    xga = float(team_stats[('Expected', 'xGA')]) if pd.notna(team_stats[('Expected', 'xGA')]) else 0
                elif 'xGA' in team_stats.index:
                    xga = float(team_stats['xGA']) if pd.notna(team_stats['xGA']) else 0

                # Matches Played
                if ('Standard', 'MP') in team_stats.index:
                    games = int(team_stats[('Standard', 'MP')]) if pd.notna(team_stats[('Standard', 'MP')]) else 0
                elif ('Playing Time', 'MP') in team_stats.index:
                    games = int(team_stats[('Playing Time', 'MP')]) if pd.notna(team_stats[('Playing Time', 'MP')]) else 0
                elif 'MP' in team_stats.index:
                    games = int(team_stats['MP']) if pd.notna(team_stats['MP']) else 0

                if games > 0:
                    seasons_data.append({
                        'season': f"{season}/{str(season+1)[-2:]}",
                        'season_year': season,
                        'xg_for': xg_for,
                        'xga': xga,
                        'games': games,
                        'xg_for_per_game': round(xg_for / games, 2),
                        'xga_per_game': round(xga / games, 2)
                    })

        except APIError:
            raise
        except requests.exceptions.RequestException as exc:
            error_msg = str(exc)
            logger.error("❌ FBref session error for %s: %s", league_code, error_msg)
            raise APIError("FBRefAPI", "NETWORK_ERROR", "Unable to fetch FBref data.", error_msg) from exc
        except Exception:
            # likely not in league this season
            pass

        # gentle pacing to avoid rate limits
        if season < current_season:
            time.sleep(2)

    if not seasons_data:
        logger.warning("⚠️  No historical xG data found for %s", team_name)
        return None

    total_xg = sum(s['xg_for'] for s in seasons_data)
    total_xga = sum(s['xga'] for s in seasons_data)
    total_games = sum(s['games'] for s in seasons_data)
    seasons_count = len(seasons_data)

    career_stats = {
        'team': team_name,
        'league': league_code,
        'seasons_count': seasons_count,
        'total_games': total_games,
        'career_xg_per_game': round(total_xg / total_games, 2) if total_games > 0 else 0,
        'career_xga_per_game': round(total_xga / total_games, 2) if total_games > 0 else 0,
        'first_season': seasons_data[0]['season'],
        'last_season': seasons_data[-1]['season'],
        'seasons_data': seasons_data
    }

    logger.info("✅ Career xG for %s: %s xG/game over %d seasons (%d games)",
                team_name, career_stats['career_xg_per_game'], seasons_count, total_games)

    CAREER_XG_CACHE[cache_key] = {
        'data': career_stats,
        'timestamp': datetime.now().timestamp()
    }
    return career_stats

# ----------------------------------------------------------------------
# League xG fetch (season aggregates)
# ----------------------------------------------------------------------


def _fetch_and_cache_league_stats_now(league_code: str, season: int) -> Dict[str, Any]:
    cache_key = get_cache_key(league_code, season)
    data = _fetch_and_cache_league_xg_stats(league_code, season, cache_key)
    if data:
        _set_mem_cache(league_code, season, data)
    return data

def _fetch_and_cache_league_xg_stats(league_code, season, cache_key):
    league_name = LEAGUE_MAPPING[league_code]

    # Handle season display
    if isinstance(season, int):
        season_display = f"{season}-{season+1}"
    else:
        season_display = str(season)
    logger.info("📊 Fetching xG stats for %s (season %s)...", league_name, season_display)

    fbref = _configure_fbref_client(sd.FBref(leagues=league_name, seasons=season))

    shooting_stats = _safe_soccerdata_call(
        fbref.read_team_season_stats,
        f"FBref shooting stats ({league_code} {season})",
        stat_type='shooting',
    )  # xG For
    standard_stats = _safe_soccerdata_call(
        fbref.read_team_season_stats,
        f"FBref standard stats ({league_code} {season})",
        stat_type='standard',
    )  # Matches played
    keeper_adv_stats = _safe_soccerdata_call(
        fbref.read_team_season_stats,
        f"FBref keeper advanced stats ({league_code} {season})",
        stat_type='keeper_adv',
    )  # Goals Against, PSxG (xGA)

    xg_data = {}

    alias_token = _league_alias_summary.set([])
    try:
        for idx, row in shooting_stats.iterrows():
            raw_team_name = idx[2] if isinstance(idx, tuple) and len(idx) >= 3 else str(idx)
            team_name = _resolve_fbref_team_name(raw_team_name, "league_xg_fetch")

            try:
                xg_for = float(row[('Expected', 'xG')])
            except (KeyError, ValueError, TypeError):
                xg_for = 0

            try:
                goals_for = int(row[('Standard', 'Gls')])
            except (KeyError, ValueError, TypeError):
                goals_for = 0

            matches_played = 0
            try:
                if idx in standard_stats.index:
                    std_row = standard_stats.loc[idx]
                    try:
                        matches_played = int(std_row[('Playing Time', 'MP')])
                    except (KeyError, ValueError, TypeError):
                        try:
                            matches_played = int(std_row[('Playing Time', '90s')])
                        except Exception:
                            matches_played = 0
            except Exception:
                pass

            goals_against = 0
            ps_xg_against = 0
            try:
                if idx in keeper_adv_stats.index:
                    keeper_row = keeper_adv_stats.loc[idx]
                    try:
                        goals_against = int(keeper_row[('Goals', 'GA')])
                    except (KeyError, ValueError, TypeError):
                        pass
                    try:
                        ps_xg_against = float(keeper_row[('Expected', 'PSxG')])
                    except (KeyError, ValueError, TypeError):
                        pass
            except Exception:
                pass

            xg_data[team_name] = {
                'xg_for': xg_for,
                'xg_against': ps_xg_against,
                'ps_xg_against': ps_xg_against,
                'matches_played': int(matches_played) if matches_played > 0 else 1,
                'goals_for': goals_for,
                'goals_against': goals_against,
            }

            if xg_data[team_name]['matches_played'] > 0:
                matches = xg_data[team_name]['matches_played']
                xg_data[team_name]['xg_for_per_game'] = round(xg_data[team_name]['xg_for'] / matches, 2)
                xg_data[team_name]['xg_against_per_game'] = round(xg_data[team_name]['xg_against'] / matches, 2)
                xg_data[team_name]['ps_xg_against_per_game'] = round(xg_data[team_name]['ps_xg_against'] / matches, 2)
                xg_data[team_name]['goals_for_per_game'] = round(xg_data[team_name]['goals_for'] / matches, 2)
                xg_data[team_name]['goals_against_per_game'] = round(xg_data[team_name]['goals_against'] / matches, 2)

                scoring_clinicality_total = xg_data[team_name]['goals_for'] - xg_data[team_name]['xg_for']
                xg_data[team_name]['scoring_clinicality'] = round(scoring_clinicality_total / matches, 2)

                ps_xg_performance = xg_data[team_name]['ps_xg_against'] - xg_data[team_name]['goals_against']
                xg_data[team_name]['ps_xg_performance'] = round(ps_xg_performance / matches, 2)
            else:
                xg_data[team_name]['xg_for_per_game'] = 0
                xg_data[team_name]['xg_against_per_game'] = 0
                xg_data[team_name]['ps_xg_against_per_game'] = 0
                xg_data[team_name]['goals_for_per_game'] = 0
                xg_data[team_name]['goals_against_per_game'] = 0
                xg_data[team_name]['scoring_clinicality'] = 0
                xg_data[team_name]['ps_xg_performance'] = 0
    finally:
        alias_changes = _league_alias_summary.get() or []
        if alias_changes:
            sample_old, sample_new = alias_changes[0]
            logger.info(
                "league_xg_fetch: applied %d alias normalizations (e.g. '%s' → '%s')",
                len(alias_changes),
                sample_old,
                sample_new,
            )
        _league_alias_summary.reset(alias_token)

    save_to_cache(cache_key, xg_data)
    logger.info("✅ Fetched xG stats for %d teams in %s", len(xg_data), league_name)
    return xg_data

def fetch_league_xg_stats(league_code, season=None, cache_only: bool = False):
    """Fetch xG statistics for all teams in a league."""

    if season is None:
        season = get_xg_season()

    mem_data, mem_age = _get_from_mem_cache(league_code, season)
    if mem_data:
        logger.info("✅ Loaded xG data for %s from in-memory cache", league_code)

        if not cache_only and _is_hard_expired(mem_age):
            try:
                fresh_data = _fetch_and_cache_league_stats_now(league_code, season)
                if fresh_data:
                    return fresh_data
                logger.warning(
                    "returning cached xg (age: %.0fs) after refresh produced empty payload",
                    mem_age,
                )
            except Exception as exc:
                logger.warning(
                    "returning cached xg (age: %.0fs) after refresh failure: %s",
                    mem_age,
                    exc,
                )
        if _is_stale(mem_age):
            logger.info(
                "returning cached xg (age: %.0fs), triggering background refresh",
                mem_age,
            )
            _refresh_league_async(league_code, season)
        return mem_data

    if cache_only:
        _refresh_league_async(league_code, season)
        return None

    cache_key = get_cache_key(league_code, season)
    cached_payload = load_from_cache(cache_key)
    if cached_payload:
        cached_data, cache_age = cached_payload
        logger.info("✅ Loaded xG data for %s from cache", league_code)
        _set_mem_cache(league_code, season, cached_data)

        if _is_hard_expired(cache_age):
            try:
                fresh_data = _fetch_and_cache_league_stats_now(league_code, season)
                if fresh_data:
                    return fresh_data
                logger.warning(
                    "returning cached xg (age: %.0fs) after refresh produced empty payload",
                    cache_age,
                )
            except Exception as exc:
                logger.warning(
                    "returning cached xg (age: %.0fs) after refresh failure: %s",
                    cache_age,
                    exc,
                )
            return cached_data

        if _is_stale(cache_age):
            logger.info(
                "returning cached xg (age: %.0fs), triggering background refresh",
                cache_age,
            )
            _refresh_league_async(league_code, season)
        return cached_data

    if league_code not in LEAGUE_MAPPING:
        logger.warning("⚠️  League %s not supported for xG stats", league_code)
        return {}

    try:
        return _fetch_and_cache_league_stats_now(league_code, season)
    except APIError:
        raise
    except requests.exceptions.RequestException as exc:
        error_msg = str(exc)
        logger.error("❌ FBref request failed for %s: %s", league_code, error_msg)
        raise APIError("FBRefAPI", "NETWORK_ERROR", "Unable to fetch xG stats.", error_msg) from exc
    except Exception:
        logger.exception("❌ Error fetching xG stats for %s", league_code)
        return {}

# ----------------------------------------------------------------------
# Team xG lookup / Match logs / Rolling / Form
# ----------------------------------------------------------------------

def safe_extract_value(row, column_name, default=None):
    """
    Safely extract a value from a pandas row, handling Series/scalar issues
    """
    try:
        value = row[column_name]
        if isinstance(value, pd.Series):
            return value.iloc[0] if len(value) > 0 else default
        return value if pd.notna(value) else default
    except (KeyError, IndexError, AttributeError):
        return default

def parse_match_result(score, is_home_team):
    """
    Parse match score to determine result (W/D/L)
    """
    if not score or pd.isna(score) or score == '':
        return None

    try:
        score_str = str(score).replace('–', '-')
        parts = score_str.split('-')
        if len(parts) != 2:
            return None

        home_goals = int(parts[0])
        away_goals = int(parts[1])

        if is_home_team:
            if home_goals > away_goals:
                return 'W'
            elif home_goals == away_goals:
                return 'D'
            else:
                return 'L'
        else:
            if away_goals > home_goals:
                return 'W'
            elif home_goals == away_goals:
                return 'D'
            else:
                return 'L'
    except Exception:
        return None

def fetch_team_match_logs(team_name, league_code, season=None, request_memo_id=None):
    """
    Fetch match-by-match logs for a team including xG and results

    Combines:
      - T30c: request memo + 60s in-mem TTL + disk cache + per-team fetch locks
      - T31: canonical FBref names via name_resolver, robust schedule matching
    """
    # Check if league is supported
    if league_code not in LEAGUE_MAPPING:
        logger.warning("⚠️  League %s not supported for match logs", league_code)
        return []

    league_name = LEAGUE_MAPPING[league_code]

    original_team_name = team_name
    team_name = _resolve_fbref_team_name(team_name, "match_logs_lookup")

    memo_id = request_memo_id or get_current_request_memo_id()
    resolved_season = season or get_xg_season()
    memo_bucket = _get_request_memo_bucket(memo_id)
    memo_key = (team_name, league_code, resolved_season)
    legacy_memo_key = (original_team_name, league_code, resolved_season)
    memo_future: Optional[Future] = None

    # --- request-scoped memo (T30c) ---
    if memo_bucket is not None:
        existing = memo_bucket.get(memo_key) or memo_bucket.get(legacy_memo_key)
        if isinstance(existing, Future):
            logger.debug("🔁 Awaiting in-flight match log fetch for %s (%s %s)", team_name, league_code, resolved_season)
            return existing.result()
        if existing is not None:
            logger.debug("✅ Using request-memoized match logs for %s (%s %s)", team_name, league_code, resolved_season)
            return existing
        memo_future = Future()
        memo_bucket[memo_key] = memo_future
        memo_bucket.pop(legacy_memo_key, None)

    def _memo_resolve_success(result):
        if memo_bucket is None:
            return
        if memo_future and not memo_future.done():
            memo_future.set_result(result)
        memo_bucket[memo_key] = result
        memo_bucket.pop(legacy_memo_key, None)

    def _memo_resolve_error(exc: Exception):
        if memo_bucket is None:
            return
        if memo_future and not memo_future.done():
            memo_future.set_exception(exc)
        memo_bucket.pop(memo_key, None)
        memo_bucket.pop(legacy_memo_key, None)

    # --- 60s in-mem TTL (T30c) ---
    season = resolved_season
    cache_lookup_key = (league_code, season, team_name)
    cached_matches = _match_logs_cache_get(cache_lookup_key)
    if cached_matches is not None:
        logger.debug("✅ Using in-memory cached match logs for %s (%s %s)", team_name, league_code, season)
        _memo_resolve_success(cached_matches)
        return cached_matches

    fetch_lock = _get_match_logs_fetch_lock(cache_lookup_key)

    with fetch_lock:
        cached_matches = _match_logs_cache_get(cache_lookup_key)
        if cached_matches is not None:
            logger.debug("✅ Using in-memory cached match logs for %s (%s %s) after lock", team_name, league_code, season)
            _memo_resolve_success(cached_matches)
            return cached_matches

        disk_cached = _load_team_match_logs_from_disk(league_code, season, team_name)
        if disk_cached is not None:
            logger.info("✅ Loaded match logs for %s from disk cache (age ≤ %ds)", team_name, MATCH_LOGS_CACHE_TTL)
            _match_logs_cache_set(cache_lookup_key, disk_cached)
            _memo_resolve_success(disk_cached)
            return disk_cached

        # --- live fetch with canonical matching (T31) ---
        try:
            logger.info("📊 Fetching match logs for %s in %s (season %s)...", team_name, league_name, season)
            fbref = _configure_fbref_client(sd.FBref(league_name, season))
            schedule = _safe_soccerdata_call(
                fbref.read_schedule,
                f"FBref schedule ({league_code} {season})",
            )

            # Add canonical columns for robust matching
            schedule = schedule.assign(
                home_team_canonical=schedule['home_team'].apply(lambda v: resolve_team_name(v, provider="fbref")),
                away_team_canonical=schedule['away_team'].apply(lambda v: resolve_team_name(v, provider="fbref")),
            )

            # Prefer canonical match; fallback to raw if needed
            home_matches = schedule[schedule['home_team_canonical'] == team_name].copy()
            away_matches = schedule[schedule['away_team_canonical'] == team_name].copy()
            if len(home_matches) == 0 and len(away_matches) == 0:
                home_matches = schedule[schedule['home_team'] == original_team_name].copy()
                away_matches = schedule[schedule['away_team'] == original_team_name].copy()

            matches = []

            # Process home matches
            for _, row in home_matches.iterrows():
                try:
                    home_xg = row['home_xg']
                    if isinstance(home_xg, pd.Series):
                        home_xg = home_xg.iloc[0] if len(home_xg) > 0 else None
                    home_xg_value = float(home_xg) if (home_xg is not None and pd.notna(home_xg)) else 0
                except Exception:
                    home_xg_value = 0

                try:
                    away_xg = row['away_xg']
                    if isinstance(away_xg, pd.Series):
                        away_xg = away_xg.iloc[0] if len(away_xg) > 0 else None
                    away_xg_value = float(away_xg) if (away_xg is not None and pd.notna(away_xg)) else 0
                except Exception:
                    away_xg_value = 0

                gameweek = None
                try:
                    gw_value = row.get('gameweek', None)
                    if gw_value is not None and pd.notna(gw_value):
                        gameweek = int(gw_value)
                except Exception:
                    pass

                match_data = {
                    'date': safe_extract_value(row, 'date'),
                    'is_home': True,
                    'opponent': safe_extract_value(row, 'away_team', 'Unknown'),
                    'gameweek': gameweek,
                    'xg_for': home_xg_value,
                    'xg_against': away_xg_value,
                    'result': parse_match_result(safe_extract_value(row, 'score'), True)
                }
                if match_data['result']:  # Only include completed matches
                    matches.append(match_data)

            # Process away matches
            for _, row in away_matches.iterrows():
                try:
                    away_xg = row['away_xg']
                    if isinstance(away_xg, pd.Series):
                        away_xg = away_xg.iloc[0] if len(away_xg) > 0 else None
                    away_xg_value = float(away_xg) if (away_xg is not None and pd.notna(away_xg)) else 0
                except Exception:
                    away_xg_value = 0

                try:
                    home_xg = row['home_xg']
                    if isinstance(home_xg, pd.Series):
                        home_xg = home_xg.iloc[0] if len(home_xg) > 0 else None
                    home_xg_value = float(home_xg) if (home_xg is not None and pd.notna(home_xg)) else 0
                except Exception:
                    home_xg_value = 0

                gameweek = None
                try:
                    gw_value = row.get('gameweek', None)
                    if gw_value is not None and pd.notna(gw_value):
                        gameweek = int(gw_value)
                except Exception:
                    pass

                match_data = {
                    'date': safe_extract_value(row, 'date'),
                    'is_home': False,
                    'opponent': safe_extract_value(row, 'home_team', 'Unknown'),
                    'gameweek': gameweek,
                    'xg_for': away_xg_value,
                    'xg_against': home_xg_value,
                    'result': parse_match_result(safe_extract_value(row, 'score'), False)
                }
                if match_data['result']:  # Only include completed matches
                    matches.append(match_data)

            # Sort by date (most recent first)
            matches.sort(key=lambda x: x['date'], reverse=True)

            logger.info("✅ Found %d completed matches for %s", len(matches), team_name)

            _match_logs_cache_set(cache_lookup_key, matches)
            _save_team_match_logs_to_disk(league_code, season, team_name, matches)

            _memo_resolve_success(matches)
            return matches

        except APIError as api_err:
            _memo_resolve_error(api_err)
            raise
        except requests.exceptions.RequestException as exc:
            _memo_resolve_error(exc)
            error_msg = str(exc)
            logger.error("❌ FBref schedule request failed for %s: %s", team_name, error_msg)
            raise APIError("FBRefAPI", "NETWORK_ERROR", "Unable to fetch match logs.", error_msg) from exc
        except Exception:
            logger.exception("❌ Error fetching match logs for %s", team_name)
            _memo_resolve_success([])
            return []


def _should_log_stacktrace_once(league_code: str, canonical_team: str) -> bool:
    now = time.monotonic()
    key = (league_code, canonical_team)
    with _stacktrace_guard_lock:
        last = _last_stacktrace_log.get(key, 0.0)
        if now - last >= REFRESH_COOLDOWN_S:
            _last_stacktrace_log[key] = now
            return True
        return False


def _ensure_team_logs_fresh(league_code: str, canonical_team: str, season: Optional[int] = None) -> None:
    try:
        fetch_team_match_logs(canonical_team, league_code, season)
        _clear_refresh_attempt(league_code, canonical_team)
    except Exception as exc:
        if _should_log_stacktrace_once(league_code, canonical_team):
            logger.exception("Error fetching match logs for %s/%s", league_code, canonical_team)
        else:
            logger.warning(
                "Match logs retry scheduled (cooldown %ss) for %s/%s: %s",
                REFRESH_COOLDOWN_S,
                league_code,
                canonical_team,
                exc,
            )

def get_team_xg_stats(team_name, league_code, season=None, league_stats=None):
    """
    Get xG statistics for a specific team
    """
    if league_stats is None:
        league_stats = fetch_league_xg_stats(league_code, season)

    if not league_stats:
        return None

    canonical_name = _resolve_fbref_team_name(team_name, "team_xg_lookup")

    if canonical_name in league_stats:
        return league_stats[canonical_name]

    if team_name in league_stats:
        return league_stats[team_name]

    for alias in get_all_aliases_for(canonical_name):
        if alias in league_stats:
            return league_stats[alias]

    team_name_lower = team_name.lower()
    for fbref_team, stats in league_stats.items():
        if (
            team_name_lower in fbref_team.lower()
            or fbref_team.lower() in team_name_lower
            or resolve_team_name(fbref_team, provider="fbref") == canonical_name
        ):
            return stats

    logger.warning("⚠️  Team '%s' not found in %s xG stats", team_name, league_code)
    return None


def _coerce_log_date(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_pydatetime"):
        try:
            converted = value.to_pydatetime()
            if isinstance(converted, datetime):
                return converted
        except Exception:
            pass
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _coerce_float(value: Any) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def compute_rolling_xg(
    team_logs: Optional[List[Dict[str, Any]]],
    N: int,
    league_only: bool = True,
    *,
    league: Optional[str] = None,
    team: Optional[str] = None,
) -> Tuple[float, float, int, str]:
    if not team_logs or N <= 0:
        return 0.0, 0.0, 0, "rolling"

    logs = list(team_logs)
    if league_only:
        logs = [log for log in logs if bool(log.get("gameweek"))]

    if not logs:
        return 0.0, 0.0, 0, "rolling"

    logs.sort(
        key=lambda log: _coerce_log_date(log.get("date")) or datetime.min,
        reverse=True,
    )

    window = max(N, 0)
    recent = logs[:window] if window else []
    window_len = len(recent)

    xg_for_sum = float(sum(_coerce_float(log.get("xg_for")) for log in recent))
    xg_against_sum = float(
        sum(_coerce_float(log.get("xg_against")) for log in recent)
    )

    if 0 < window_len < window:
        league_key = league or ""
        team_key = team or ""
        warning_key = (league_key, team_key, window)
        if warning_key not in _PARTIAL_WINDOW_WARNINGS:
            _PARTIAL_WINDOW_WARNINGS.add(warning_key)
            logger.warning(
                "⚠️ partial rolling window for %s in %s: expected %s, got %s",
                team,
                league,
                window,
                window_len,
            )

    return xg_for_sum, xg_against_sum, window_len, "rolling"


def get_team_recent_xg_snapshot(
    team: str,
    league: str,
    season: int,
    window: int = 4,
) -> Dict[str, Any]:
    window = max(window, 0)

    logs = fetch_team_match_logs(team, league, season)

    compute_fn = compute_rolling_xg
    try:
        from . import request_memo as _request_memo  # type: ignore

        memo_compute = getattr(_request_memo, "compute_rolling_xg", None)
        if callable(memo_compute):
            compute_fn = memo_compute  # type: ignore[assignment]
    except Exception:
        pass

    xg_for_sum, xg_against_sum, window_len, source = compute_fn(
        logs or [],
        window,
        league_only=True,
        league=league,
        team=team,
    )

    if window_len > 0:
        return {
            "xg_for_sum": float(xg_for_sum),
            "xg_against_sum": float(xg_against_sum),
            "window_len": window_len,
            "source": source,
        }

    table = fetch_league_xg_stats(league, season, cache_only=True)
    if not table:
        return {
            "xg_for_sum": 0.0,
            "xg_against_sum": 0.0,
            "window_len": 0,
            "source": "rolling",
        }

    team_row = get_team_xg_stats(team, league, season, league_stats=table)
    if not team_row:
        return {
            "xg_for_sum": 0.0,
            "xg_against_sum": 0.0,
            "window_len": 0,
            "source": "rolling",
        }

    def _per_match(stats: Dict[str, Any], candidates: List[str], total_key: str) -> float:
        for key in candidates:
            value = stats.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        total = stats.get(total_key)
        matches = stats.get("matches_played") or stats.get("matches")
        if matches and total is not None:
            try:
                matches_f = float(matches)
                total_f = float(total)
                if matches_f:
                    return total_f / matches_f
            except (TypeError, ValueError, ZeroDivisionError):
                return 0.0
        return 0.0

    per_match_for = _per_match(
        team_row,
        ["xg_for_per_match", "xg_for_per_game"],
        "xg_for",
    )
    per_match_against = _per_match(
        team_row,
        ["xg_against_per_match", "xg_against_per_game", "ps_xg_against_per_game"],
        "xg_against",
    )
    if not per_match_against:
        per_match_against = _per_match(
            team_row,
            ["ps_xg_against_per_game"],
            "ps_xg_against",
        )

    return {
        "xg_for_sum": float(per_match_for * window),
        "xg_against_sum": float(per_match_against * window),
        "window_len": window,
        "source": "season",
    }


def calculate_rolling_averages(matches, window=5):
    """
    Calculate rolling averages for xG metrics
    """
    if len(matches) < window:
        window = len(matches)

    if window == 0:
        return {'xg_for_rolling': 0, 'xg_against_rolling': 0, 'matches_count': 0}

    recent_matches = matches[:window]
    xg_for_total = sum(m['xg_for'] for m in recent_matches)
    xg_against_total = sum(m['xg_against'] for m in recent_matches)

    return {
        'xg_for_rolling': round(xg_for_total / window, 2),
        'xg_against_rolling': round(xg_against_total / window, 2),
        'matches_count': window
    }

def extract_last_5_results(matches, limit=5):
    """
    Extract last N match results as form string
    """
    if len(matches) < limit:
        limit = len(matches)
    form = ''.join([m['result'] for m in matches[:limit] if m['result']])
    return form


def _get_cached_team_logs_in_memory(
    league_code: str, season: int, canonical_team: str
) -> Optional[Any]:
    key = (league_code, season, canonical_team)
    cached = _match_logs_cache_get(key)
    if cached is not None:
        return cached

    for alias in get_all_aliases_for(canonical_team):
        alias_key = (league_code, season, alias)
        cached_alias = _match_logs_cache_get(alias_key)
        if cached_alias is not None:
            return cached_alias
    return None


def _build_prediction_payload(
    home_team: str,
    away_team: str,
    home_stats: Dict[str, Any],
    away_stats: Dict[str, Any],
    home_matches: Optional[Any],
    away_matches: Optional[Any],
):
    home_matches = list(home_matches or [])
    away_matches = list(away_matches or [])

    home_rolling = {'xg_for_rolling': None, 'xg_against_rolling': None, 'matches_count': 0}
    away_rolling = {'xg_for_rolling': None, 'xg_against_rolling': None, 'matches_count': 0}
    home_form = None
    away_form = None
    home_recent_matches = []
    away_recent_matches = []

    if home_matches:
        home_rolling = calculate_rolling_averages(home_matches, 5)
        home_form = extract_last_5_results(home_matches, 5)
        home_recent_matches = [{
            'date': str(m['date']),
            'opponent': m['opponent'],
            'is_home': m['is_home'],
            'xg_for': m['xg_for'],
            'xg_against': m['xg_against'],
            'result': m['result']
        } for m in home_matches[:5]]

    if away_matches:
        away_rolling = calculate_rolling_averages(away_matches, 5)
        away_form = extract_last_5_results(away_matches, 5)
        away_recent_matches = [{
            'date': str(m['date']),
            'opponent': m['opponent'],
            'is_home': m['is_home'],
            'xg_for': m['xg_for'],
            'xg_against': m['xg_against'],
            'result': m['result']
        } for m in away_matches[:5]]

    home_advantage_factor = 1.15

    use_home_rolling = (
        home_rolling['matches_count'] >= 3 and home_rolling['xg_for_rolling'] is not None
    )
    use_away_rolling = (
        away_rolling['matches_count'] >= 3 and away_rolling['xg_for_rolling'] is not None
    )

    home_xgf = home_rolling['xg_for_rolling'] if use_home_rolling else home_stats['xg_for_per_game']
    home_xga = home_rolling['xg_against_rolling'] if use_home_rolling else home_stats['xg_against_per_game']
    away_xgf = away_rolling['xg_for_rolling'] if use_away_rolling else away_stats['xg_for_per_game']
    away_xga = away_rolling['xg_against_rolling'] if use_away_rolling else away_stats['xg_against_per_game']

    home_xg = ((home_xgf + away_xga) / 2) * home_advantage_factor
    away_xg = (away_xgf + home_xga) / 2

    total_xg = home_xg + away_xg

    over_2_5_probability = min(95, max(5, int((total_xg - 2.5) * 30 + 50)))

    if home_xg - away_xg > 0.5:
        result_prediction = "HOME_WIN"
        confidence = min(80, int(40 + (home_xg - away_xg) * 20))
    elif away_xg - home_xg > 0.5:
        result_prediction = "AWAY_WIN"
        confidence = min(80, int(40 + (away_xg - home_xg) * 20))
    else:
        result_prediction = "DRAW"
        confidence = min(60, int(30 + abs(home_xg - away_xg) * 10))

    return {
        'available': True,
        'home_team': home_team,
        'away_team': away_team,
        'home_xg': round(home_xg, 2),
        'away_xg': round(away_xg, 2),
        'total_xg': round(total_xg, 2),
        'data_source_home': 'rolling_5' if use_home_rolling else 'season_avg',
        'data_source_away': 'rolling_5' if use_away_rolling else 'season_avg',
        'home_stats': {
            'xg_for_per_game': home_stats['xg_for_per_game'],
            'xg_against_per_game': home_stats['xg_against_per_game'],
            'scoring_clinicality': home_stats['scoring_clinicality'],
            'rolling_5': home_rolling,
            'form': home_form,
            'recent_matches': home_recent_matches,
            'using_rolling': use_home_rolling
        },
        'away_stats': {
            'xg_for_per_game': away_stats['xg_for_per_game'],
            'xg_against_per_game': away_stats['xg_against_per_game'],
            'scoring_clinicality': away_stats['scoring_clinicality'],
            'rolling_5': away_rolling,
            'form': away_form,
            'recent_matches': away_recent_matches,
            'using_rolling': use_away_rolling
        },
        'over_under_2_5': {
            'prediction': 'OVER' if over_2_5_probability > 50 else 'UNDER',
            'over_probability': over_2_5_probability,
            'under_probability': 100 - over_2_5_probability
        },
        'result_prediction': {
            'prediction': result_prediction,
            'confidence': confidence
        }
    }


def _pick_effective_league(
    requested_league: str, canonical_home: str, canonical_away: str
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    if requested_league in LEAGUE_MAPPING:
        return requested_league, None

    inferred = _infer_domestic_league_for_both(canonical_home, canonical_away)
    if inferred:
        logger.info(
            "🌍 Cross-competition fallback: %s → %s for %s vs %s",
            requested_league,
            inferred,
            canonical_home,
            canonical_away,
        )
        return inferred, None

    if requested_league in ['CL', 'EL']:
        league_name = 'Champions League' if requested_league == 'CL' else 'Europa League'
        return None, {
            'available': False,
            'error': (
                f'xG data not available for {league_name} '
                '(FBref is domestic-only; supported domestic leagues: '
                'Premier League, La Liga, Bundesliga, Serie A, Ligue 1)'
            )
        }

    return None, {
        'available': False,
        'error': 'xG data not available for this competition (FBref is domestic-only).'
    }

def get_match_xg_prediction(home_team, away_team, league_code, season=None):
    """
    Generate xG-based prediction for a match
    """
    canonical_home = _resolve_fbref_team_name(home_team, "match_xg_home")
    canonical_away = _resolve_fbref_team_name(away_team, "match_xg_away")

    effective_league, error_payload = _pick_effective_league(
        league_code, canonical_home, canonical_away
    )
    if not effective_league:
        return error_payload

    resolved_season = season or get_xg_season()
    table = fetch_league_xg_stats(effective_league, season=season, cache_only=True)
    if not table:
        return {
            'available': False,
            'error': 'xG data not available right now (warming). Try again in a moment.'
        }

    home_stats = get_team_xg_stats(
        canonical_home, effective_league, season, league_stats=table
    )
    away_stats = get_team_xg_stats(
        canonical_away, effective_league, season, league_stats=table
    )

    if not home_stats or not away_stats:
        if league_code in ['CL', 'EL']:
            league_name = 'Champions League' if league_code == 'CL' else 'Europa League'
            return {
                'available': False,
                'error': (
                    f'xG data not available for {league_name} '
                    '(FBref is domestic-only; supported domestic leagues: '
                    'Premier League, La Liga, Bundesliga, Serie A, Ligue 1)'
                )
            }
        return {'available': False, 'error': DOMESTIC_MAPPING_FALLBACK_MESSAGE}

    home_matches = _get_cached_team_logs_in_memory(
        effective_league, resolved_season, canonical_home
    )
    away_matches = _get_cached_team_logs_in_memory(
        effective_league, resolved_season, canonical_away
    )

    payload = _build_prediction_payload(
        home_team,
        away_team,
        home_stats,
        away_stats,
        home_matches or [],
        away_matches or [],
    )

    # Non-blocking background warmers (debounced)
    _refresh_logs_async(effective_league, canonical_home, resolved_season)
    _refresh_logs_async(effective_league, canonical_away, resolved_season)

    if not home_matches or not away_matches:
        payload.setdefault(
            'note',
            'Using cached season xG; rolling form is warming…'
        )

    return payload

# ----------------------------------------------------------------------
# Manual test
# ----------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Testing xG Data Fetcher...")

    stats = fetch_league_xg_stats("PL")
    if stats:
        logger.info("Found %d teams", len(stats))
        first_team = list(stats.keys())[0]
        logger.info("Example - %s:", first_team)
        logger.info(json.dumps(stats[first_team], indent=2))

    logger.info("=" * 50)
    prediction = get_match_xg_prediction("Arsenal", "Chelsea", "PL")
    logger.info("Match Prediction:")
    logger.info(json.dumps(prediction, indent=2))
