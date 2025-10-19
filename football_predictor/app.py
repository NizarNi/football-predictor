from flask import Flask, render_template, request, url_for, current_app, g
import os
from datetime import datetime, timezone
import base64
import binascii
import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from threading import Lock, Thread
from concurrent.futures import TimeoutError as FuturesTimeoutError
from time import monotonic
from typing import Any, Optional
from types import SimpleNamespace

from .config import setup_logger, API_TIMEOUT_CONTEXT

from .app_utils import make_ok, make_error, legacy_endpoint, update_server_context
from .logo_resolver import resolve_logo

# Import our custom modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# football-data.org API removed - using Understat as primary source for standings
from .odds_api_client import get_upcoming_matches_with_odds, LEAGUE_CODE_MAPPING
from .odds_calculator import calculate_predictions_from_odds
from .xg_data_fetcher import (
    clear_request_memo_id,
    get_match_xg_prediction,
    get_team_recent_xg_snapshot,
    set_request_memo_id,
    warm_top5_leagues,
)
from .utils import get_current_season, fuzzy_team_match
from .name_resolver import (
    alias_logging_context,
    resolve_team_name,
    warm_alias_resolver,
)
from .errors import APIError
from .validators import (
    validate_league,
    validate_next_n_days,
    validate_team_optional,
)
from .request_memo import RequestMemo

PKG_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(PKG_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config['TEMPLATES_AUTO_RELOAD'] = True

logger = setup_logger(__name__)

# Always register FotMob blueprints (no feature flag)
try:
    from football_predictor.routes.fotmob import bp as fotmob_page_bp
    from football_predictor.routes.fotmob_api import bp as fotmob_api_bp
    app.register_blueprint(fotmob_page_bp)
    app.register_blueprint(fotmob_api_bp)
    app.logger.info("fotmob_routes_registered: always-on")
except Exception as e:  # pragma: no cover - log blueprint registration errors
    app.logger.exception("fotmob_routes_register_failed: %s", e)

# Warm alias resolver at startup to avoid lazy initialization gaps (T37).
_ALIAS_PROVIDERS = warm_alias_resolver()

xg_prefetch_ready = os.environ.get("XG_PREFETCH_READY", "").lower() in {
    "1",
    "true",
    "yes",
}
_xg_prefetch_lock = Lock()
_xg_prefetch_started = False


def _start_xg_prefetch_async() -> None:
    global _xg_prefetch_started, xg_prefetch_ready

    if xg_prefetch_ready:
        return

    with _xg_prefetch_lock:
        if _xg_prefetch_started or xg_prefetch_ready:
            return
        _xg_prefetch_started = True

    def _runner() -> None:
        global xg_prefetch_ready
        try:
            warm_top5_leagues()
        except Exception:  # pragma: no cover - best effort logging
            logger.exception("xg_prefetch: startup warm failed")
        finally:
            xg_prefetch_ready = True

    Thread(target=_runner, name="xg-prefetch", daemon=True).start()

# ---- universal warm-up hook ----
def _prefetch_top_leagues() -> None:
    """Pre-warm xG caches for top-5 leagues once on startup."""
    try:
        if not xg_prefetch_ready:
            logger.info("🔥 Prewarming top-5 league xG caches…")
            _start_xg_prefetch_async()
    except Exception:
        logger.exception("⚠️ xg_prefetch: startup warm-up failed")

# Trigger immediately on import so it runs once when app starts
_prefetch_top_leagues()
# ---- end warm-up hook ----

def _apply_recent_xg_context(
    home_team: Optional[str],
    away_team: Optional[str],
    league_code: Optional[str],
    season: Optional[int] = None,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    if not home_team or not away_team or not league_code:
        return None, None

    try:
        home_snapshot = get_team_recent_xg_snapshot(home_team, league_code, season=season)
        away_snapshot = get_team_recent_xg_snapshot(away_team, league_code, season=season)
    except Exception:
        logger.debug("recent_xg_context: snapshot fetch failed", exc_info=True)
        return None, None

    def _avg(snapshot: dict[str, Any], key: str) -> Optional[float]:
        window_len = snapshot.get("window_len") or 0
        if window_len <= 0:
            return None
        value = snapshot.get(key)
        try:
            return round(float(value) / window_len, 2)
        except (TypeError, ZeroDivisionError):
            return None

    window_len = min(
        home_snapshot.get("window_len", 0),
        away_snapshot.get("window_len", 0),
    )
    if window_len <= 0:
        window_len = max(
            home_snapshot.get("window_len", 0),
            away_snapshot.get("window_len", 0),
        )

    update_server_context(
        {
            "team_recent_xg_for": _avg(home_snapshot, "xg_for_sum"),
            "team_recent_xg_against": _avg(home_snapshot, "xg_against_sum"),
            "opp_recent_xg_for": _avg(away_snapshot, "xg_for_sum"),
            "opp_recent_xg_against": _avg(away_snapshot, "xg_against_sum"),
            "recent_xg_window_len": int(window_len) if window_len else None,
        }
    )

    return home_snapshot, away_snapshot


def _normalize_xg_metadata(prediction: dict[str, Any]) -> dict[str, Any]:
    fast_path = bool(prediction.get("fast_path"))
    completeness = prediction.get("completeness")
    if completeness is None:
        completeness = "season_only" if fast_path else "season+logs"
    availability = prediction.get("availability")
    if not availability:
        availability = "available" if prediction.get("available") else "unavailable"
    refresh_status = prediction.get("refresh_status")
    if not refresh_status:
        refresh_status = "ready" if not fast_path else "warming"
    resolver_seed = bool(prediction.get("resolver_seed"))
    metadata: dict[str, Any] = {
        "fast_path": fast_path,
        "completeness": completeness,
        "refresh_status": refresh_status,
        "availability": availability,
        "resolver_seed": resolver_seed,
    }
    if prediction.get("reason") is not None:
        metadata["reason"] = prediction.get("reason")
    if prediction.get("note"):
        metadata["note"] = prediction.get("note")
    phase = prediction.get("refresh_phase")
    if not phase:
        if not fast_path or refresh_status == "ready":
            phase = "ready" if not fast_path else "season_snapshot"
        else:
            phase = "warming"
    metadata["refresh_phase"] = phase
    return metadata


@app.before_request
def _prime_request_memo() -> None:
    clear_request_memo_id()
    request_id = uuid.uuid4().hex
    g._xg_request_memo_id = request_id
    g._server_context = {}
    set_request_memo_id(request_id)
    g.ctx = SimpleNamespace()
    g.ctx.memo = RequestMemo()


@app.teardown_request
def _clear_request_memo(_exc: Optional[BaseException]) -> None:
    try:
        clear_request_memo_id()
    finally:
        if hasattr(g, "pop"):
            g.pop("_xg_request_memo_id", None)
            # Keep both: ctx (T35f memo container) and _server_context (existing internal context)
            g.pop("ctx", None)
            g.pop("_server_context", None)

# ---- T29c: small Elo reuse caches (in-process) ----
_RECENT_ELO_TTL_SEC = 30 * 60  # 30 minutes
_recent_elo: dict[str, tuple[float, float]] = {}

_recent_match_elo_ttl_sec = 30 * 60
_recent_match_elo: dict[str, tuple[tuple[Optional[float], Optional[float]], float]] = {}
_ELO_HINT_MAX_AGE_SEC = 60 * 60


def _norm_team_key(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    from .utils import normalize_team_name

    return normalize_team_name(name).strip().lower()


def _parse_header_elo_hint(raw_header: Optional[str]) -> Optional[dict[str, Any]]:
    if not raw_header:
        return None
    candidate = raw_header.strip()
    if not candidate:
        return None

    decoded = candidate
    try:
        decoded_bytes = base64.b64decode(candidate, validate=True)
        decoded = decoded_bytes.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        decoded = candidate

    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _merge_elo_hints(base: Optional[dict[str, Any]], override: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not base:
        return override
    if not override:
        return base

    merged = {**base}
    for key, value in override.items():
        if key == "teams" and isinstance(value, dict):
            base_teams = merged.get("teams")
            if isinstance(base_teams, dict):
                merged["teams"] = {**base_teams, **value}
            else:
                merged["teams"] = {**value}
        else:
            merged[key] = value
    return merged


def _coerce_elo_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            parsed = float(candidate)
        except ValueError:
            return None
        return parsed
    return None


def _elo_cache_get(team_name: Optional[str]) -> Optional[float]:
    key = _norm_team_key(team_name)
    if not key:
        return None
    rec = _recent_elo.get(key)
    if not rec:
        return None
    elo, ts = rec
    if monotonic() - ts > _RECENT_ELO_TTL_SEC:
        _recent_elo.pop(key, None)
        return None
    return elo


def _elo_cache_put(team_name: Optional[str], elo: Optional[float]) -> None:
    if elo is None:
        return
    key = _norm_team_key(team_name)
    if not key:
        return
    _recent_elo[key] = (elo, monotonic())


def _match_elo_cache_put(
    event_id: Optional[str], home_elo: Optional[float], away_elo: Optional[float]
) -> None:
    if not event_id:
        return
    _recent_match_elo[event_id] = ((home_elo, away_elo), monotonic())


def _match_elo_cache_get(event_id: Optional[str]) -> tuple[Optional[float], Optional[float]] | None:
    if not event_id:
        return None
    rec = _recent_match_elo.get(event_id)
    if not rec:
        return None
    (home_elo, away_elo), ts = rec
    if monotonic() - ts > _recent_match_elo_ttl_sec:
        _recent_match_elo.pop(event_id, None)
        return None
    return (home_elo, away_elo)


# ---- end T29c helpers ----

# Logo helpers

def to_static_url(abs_path: str) -> str:
    """
    Convert an absolute path under app.static_folder into a /static/... URL.
    Falls back to generic shield if anything goes wrong.
    """
    try:
        static_root = current_app.static_folder
        rel = os.path.relpath(abs_path, static_root)
        rel = rel.replace(os.sep, "/")
        return url_for("static", filename=rel)
    except Exception:
        return url_for("static", filename="team_logos/generic_shield.svg")


def build_team_logo_urls(home_team: Optional[str], away_team: Optional[str]) -> tuple[str, str]:
    home_logo_ref = resolve_logo(home_team)
    away_logo_ref = resolve_logo(away_team)

    home_logo_url = (
        home_logo_ref
        if isinstance(home_logo_ref, str) and home_logo_ref.startswith("http")
        else to_static_url(home_logo_ref)
    )
    away_logo_url = (
        away_logo_ref
        if isinstance(away_logo_ref, str) and away_logo_ref.startswith("http")
        else to_static_url(away_logo_ref)
    )

    return home_logo_url, away_logo_url

# Global variables
# Note: Matches fetched from The Odds API, standings from Understat


def _get_request_memo() -> Optional[RequestMemo]:
    ctx = getattr(g, "ctx", None)
    if ctx is None:
        return None
    return getattr(ctx, "memo", None)


def _ensure_rolling_fields(
    memo: Optional[RequestMemo],
    league: Optional[str],
    home_team: Optional[str],
    away_team: Optional[str],
    target: dict,
) -> None:
    if memo is None or not league or not home_team or not away_team:
        return

    home = memo.get_or_compute_rolling(home_team, league)
    away = memo.get_or_compute_rolling(away_team, league)

    target.setdefault(
        "rolling_xg_home",
        {
            "for": [],
            "against": [],
            "dates": [],
            "window_len": 0,
            "source_label": "league_only",
        },
    )
    target.setdefault(
        "rolling_xg_away",
        {
            "for": [],
            "against": [],
            "dates": [],
            "window_len": 0,
            "source_label": "league_only",
        },
    )

    if home:
        target["rolling_xg_home"] = {
            "for": home.get("for", []),
            "against": home.get("against", []),
            "dates": home.get("dates", []),
            "window_len": home.get("window_len", 0),
            "source_label": home.get("source_label"),
        }
        target["xg_cache_source_home"] = home.get("cache_source")

    if away:
        target["rolling_xg_away"] = {
            "for": away.get("for", []),
            "against": away.get("against", []),
            "dates": away.get("dates", []),
            "window_len": away.get("window_len", 0),
            "source_label": away.get("source_label"),
        }
        target["xg_cache_source_away"] = away.get("cache_source")


def _assemble_match_context_core(
    league: str,
    home_team: Optional[str],
    away_team: Optional[str],
    event_id: Optional[str],
    elo_hint: Optional[dict[str, Any]] = None,
) -> dict:
    from .understat_client import fetch_understat_standings
    from .elo_client import calculate_elo_probabilities

    # ---- T29c: try to reuse Elo from recent caches BEFORE calling ClubElo ----
    home_elo = None
    away_elo = None
    hint_used = False
    cache_log_emitted = False

    cached_pair = _match_elo_cache_get(event_id)
    if cached_pair is not None:
        home_elo, away_elo = cached_pair

    if home_elo is None and home_team:
        home_elo = _elo_cache_get(home_team)
    if away_elo is None and away_team:
        away_elo = _elo_cache_get(away_team)

    def log_cache_result(he: Optional[float], ae: Optional[float], label: str) -> None:
        nonlocal cache_log_emitted
        segments: list[str] = []
        if he is not None:
            segments.append("home")
        if ae is not None:
            segments.append("away")
        status = "hit" if segments else "miss"
        extra = {
            "match_id": event_id,
            "segments": segments,
            "label": label,
            "hint_used": hint_used,
        }
        log_fn = logger.info if segments else logger.warning
        log_fn("context_core: cache-only Elo %s", status, extra=extra)
        cache_log_emitted = True

    # Prefer client-provided Elo hints when fresh enough
    if elo_hint:
        hint_home = _coerce_elo_value(elo_hint.get("home"))
        hint_away = _coerce_elo_value(elo_hint.get("away"))
        raw_ts = elo_hint.get("ts")
        hint_timestamp: Optional[datetime] = None
        if isinstance(raw_ts, (int, float)):
            try:
                hint_timestamp = datetime.fromtimestamp(raw_ts, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                hint_timestamp = None
        elif isinstance(raw_ts, str):
            try:
                hint_timestamp = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                if hint_timestamp.tzinfo is None:
                    hint_timestamp = hint_timestamp.replace(tzinfo=timezone.utc)
            except ValueError:
                hint_timestamp = None

        hint_age_seconds: Optional[float] = None
        if hint_timestamp is not None:
            hint_age_seconds = (datetime.now(timezone.utc) - hint_timestamp).total_seconds()
        if hint_age_seconds is not None and hint_age_seconds < 0:
            hint_age_seconds = 0.0

        within_ttl = (
            hint_age_seconds is None or hint_age_seconds <= _ELO_HINT_MAX_AGE_SEC
        )

        if within_ttl:
            if home_elo is None and hint_home is not None:
                home_elo = hint_home
                hint_used = True
            if away_elo is None and hint_away is not None:
                away_elo = hint_away
                hint_used = True
            if hint_used:
                age_minutes = 0
                if hint_age_seconds is not None:
                    age_minutes = int(round(hint_age_seconds / 60))
                logger.info(
                    "context_core: using elo hint (age: %sm)",
                    age_minutes,
                    extra={
                        "match_id": event_id,
                        "hint_home": bool(hint_home is not None),
                        "hint_away": bool(hint_away is not None),
                        "fingerprint": elo_hint.get("fingerprint"),
                    },
                )
                if home_team and home_elo is not None:
                    _elo_cache_put(home_team, home_elo)
                if away_team and away_elo is not None:
                    _elo_cache_put(away_team, away_elo)
                if event_id:
                    _match_elo_cache_put(event_id, home_elo, away_elo)
            else:
                teams_hint = elo_hint.get("teams")
                if isinstance(teams_hint, dict):
                    for hinted_name, hinted_value in teams_hint.items():
                        hinted_rating = (
                            _coerce_elo_value(hinted_value.get("rating"))
                            if isinstance(hinted_value, dict)
                            else _coerce_elo_value(hinted_value)
                        )
                        if hinted_rating is not None:
                            _elo_cache_put(hinted_name, hinted_rating)
        else:
            logger.info(
                "context_core: elo hint stale (age: %.1fh)",
                (hint_age_seconds or 0) / 3600,
                extra={
                    "match_id": event_id,
                    "fingerprint": elo_hint.get("fingerprint"),
                },
            )
    # ---- end T29c reuse ----

    current_season = get_current_season()
    logger.info("📊 Fetching standings from Understat", extra={"season": current_season})

    start_time = time.monotonic()
    standings = None
    source = None
    missing_sources: list[str] = []
    timeout_missing: list[str] = []

    def fetch_elos():
        from .elo_client import get_team_elo

        he = home_elo
        ae = away_elo
        try:
            if he is None and home_team:
                he = get_team_elo(home_team, allow_network=False)
                _elo_cache_put(home_team, he)
            if ae is None and away_team:
                ae = get_team_elo(away_team, allow_network=False)
                _elo_cache_put(away_team, ae)
        except Exception as elo_err:
            logger.warning(
                "Context: Elo fetch issue: %s",
                getattr(elo_err, "code", type(elo_err).__name__),
            )
        log_cache_result(he, ae, "thread")
        return (he, ae)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            "understat": executor.submit(fetch_understat_standings, league, current_season),
        }
        if home_elo is None or away_elo is None:
            futures["elo"] = executor.submit(fetch_elos)

        done, _ = wait(futures.values(), timeout=API_TIMEOUT_CONTEXT)

        for key, future in futures.items():
            if future in done:
                try:
                    result = future.result()
                    if key == "understat":
                        standings = result
                        source = "Understat" if standings else None
                    elif key == "elo":
                        home_elo, away_elo = result
                except APIError as api_err:
                    logger.warning(
                        "API error from %s: %s",
                        key,
                        getattr(api_err, "message", str(api_err)),
                    )
                    missing_sources.append(key)
                except (ValueError, KeyError) as parse_err:
                    logger.warning("Parse error from %s: %s", key, parse_err)
                    missing_sources.append(key)
                except FuturesTimeoutError:
                    logger.warning("Timeout retrieving future for %s", key)
                    missing_sources.append(key)
                except Exception as unexpected:
                    logger.exception("Unexpected error from %s", key)
                    missing_sources.append(key)
            else:
                future.cancel()
                logger.warning("Timeout retrieving future for %s", key)
                missing_sources.append(key)
                timeout_missing.append(key)

    if not cache_log_emitted:
        log_cache_result(home_elo, away_elo, "prefetch")

    timed_out = bool(timeout_missing)
    if timed_out:
        elapsed = time.monotonic() - start_time
        logger.warning("[ContextFetcher] Timeout after %.2fs – served partial data.", elapsed)
    elif missing_sources:
        logger.warning("[ContextFetcher] Partial data due to errors: %s", missing_sources)

    if event_id:
        _match_elo_cache_put(event_id, home_elo, away_elo)

    if home_elo is None and away_elo is None:
        logger.warning(
            "context_core: Elo unavailable after cache-only lookup",
            extra={"match_id": event_id, "hint_used": hint_used},
        )

    elo_probs = (
        calculate_elo_probabilities(home_elo, away_elo)
        if home_elo and away_elo
        else None
    )

    home_data = None
    away_data = None

    if standings and home_team:
        home_data = next((team for team in standings if fuzzy_team_match(team['name'], home_team)), None)

    if standings and away_team:
        away_data = next((team for team in standings if fuzzy_team_match(team['name'], away_team)), None)

    if home_data and away_data:
        narrative = generate_match_narrative(home_data, away_data)
        if source:
            logger.info("✅ Standings fetched", extra={"source": source})
    elif home_data or away_data:
        narrative = "Partial standings available. Full context data unavailable for this match."
    else:
        narrative = (
            f"Standings not available for {league}. This may be a cup competition or teams not found in league standings."
        )

    season_start = current_season - 1
    season_display = f"{season_start}/{str(current_season)[-2:]}"

    home_logo_url, away_logo_url = build_team_logo_urls(home_team, away_team)

    context = {
        "home_team": {
            "position": home_data.get('position') if home_data else None,
            "points": home_data.get('points') if home_data else None,
            "form": home_data.get('form') if home_data else None,
            "name": home_team,
            "logo_url": home_logo_url,
            "ppda_coef": home_data.get('ppda_coef') if home_data else None,
            "oppda_coef": home_data.get('oppda_coef') if home_data else None,
            "xG": home_data.get('xG') if home_data else None,
            "xGA": home_data.get('xGA') if home_data else None,
            "elo_rating": home_elo,
            "played": home_data.get('match_count', home_data.get('played', 0)) if home_data else 0,
            "xg_percentile": home_data.get('xg_percentile') if home_data else None,
            "xga_percentile": home_data.get('xga_percentile') if home_data else None,
            "ppda_percentile": home_data.get('ppda_percentile') if home_data else None,
            "attack_rating": home_data.get('attack_rating') if home_data else None,
            "defense_rating": home_data.get('defense_rating') if home_data else None,
            "league_stats": home_data.get('league_stats') if home_data else None,
            "recent_trend": home_data.get('recent_trend') if home_data else None,
        },
        "away_team": {
            "position": away_data.get('position') if away_data else None,
            "points": away_data.get('points') if away_data else None,
            "form": away_data.get('form') if away_data else None,
            "name": away_team,
            "logo_url": away_logo_url,
            "ppda_coef": away_data.get('ppda_coef') if away_data else None,
            "oppda_coef": away_data.get('oppda_coef') if away_data else None,
            "xG": away_data.get('xG') if away_data else None,
            "xGA": away_data.get('xGA') if away_data else None,
            "elo_rating": away_elo,
            "played": away_data.get('match_count', away_data.get('played', 0)) if away_data else 0,
            "xg_percentile": away_data.get('xg_percentile') if away_data else None,
            "xga_percentile": away_data.get('xga_percentile') if away_data else None,
            "ppda_percentile": away_data.get('ppda_percentile') if away_data else None,
            "attack_rating": away_data.get('attack_rating') if away_data else None,
            "defense_rating": away_data.get('defense_rating') if away_data else None,
            "league_stats": away_data.get('league_stats') if away_data else None,
            "recent_trend": away_data.get('recent_trend') if away_data else None,
        },
        "elo_predictions": elo_probs,
        "narrative": narrative,
        "has_data": bool(home_data or away_data),
        "source": source,
        "season_display": season_display,
        "home_logo_url": home_logo_url,
        "away_logo_url": away_logo_url,
    }

    if elo_probs:
        logger.info(
            "✅ Elo predictions computed",
            extra={
                "home_win": elo_probs['home_win'],
                "draw": elo_probs['draw'],
                "away_win": elo_probs['away_win'],
            },
        )

    if timed_out:
        context.update(
            {
                "partial": True,
                "missing": sorted(set(timeout_missing)),
                "source": "partial_timeout",
                "warning": "context timeout",
            }
        )
        if source:
            context["standings_source"] = source
    else:
        context["source"] = source

    return context

@app.route("/")
def index():
    """Render the home page"""
    return render_template("index.html")

@app.route("/learn")
def learn():
    """Educational page about football analytics and betting strategies"""
    return render_template("learn.html")

@app.route("/demo")
def demo():
    """Demo page to showcase Over/Under and Match Context features (static version)"""
    try:
        with open('/tmp/demo_static.html', 'r') as f:
            return f.read()
    except:
        return "Demo page not available", 404


@app.route("/status", methods=["GET"])
def status():
    """Health-check endpoint reporting response format mode."""
    from .config import USE_LEGACY_RESPONSES

    return make_ok({"legacy_mode": USE_LEGACY_RESPONSES})


@app.route("/health", methods=["GET"])
def health():
    return make_ok(
        {"ok": True, "ts": datetime.now(timezone.utc).isoformat()},
        "OK",
        status_code=200,
    )

@app.route("/upcoming", methods=["GET"])
@legacy_endpoint
def upcoming():
    """Get upcoming matches with predictions using The Odds API (primary) and football-data.org (fallback)"""
    league, _lw = validate_league(request.args.get("league"))
    next_n_days, _nw = validate_next_n_days(request.args.get("next_n_days"))
    home_team, _ = validate_team_optional(request.args.get("home_team"))
    away_team, _ = validate_team_optional(request.args.get("away_team"))

    try:
        logger.info("Handling /upcoming request", extra={
            "league": league,
            "next_n_days": next_n_days,
            "home_team": home_team,
            "away_team": away_team,
        })
        # Try The Odds API first (provides both matches and odds-based predictions)
        logger.info("🔍 Fetching matches with odds from The Odds API...")
        try:
            if league:
                leagues_to_fetch = [league]
            else:
                leagues_to_fetch = list(LEAGUE_CODE_MAPPING.keys())

            odds_matches = get_upcoming_matches_with_odds(league_codes=leagues_to_fetch, next_n_days=next_n_days)

            if odds_matches:
                # Import Elo client for predictions
                from .elo_client import (
                    calculate_elo_probabilities,
                    get_team_elo,
                    elo_is_unhealthy,
                )

                elo_budget = 3  # at most 3 network-backed Elo pairs per request
                elo_pair_attempts = 0
                elo_cache_local: dict[str, Optional[float]] = {}

                # Calculate predictions from odds for each match
                for match in odds_matches:
                    predictions = calculate_predictions_from_odds(match)

                    # Format match data
                    match["datetime"] = match["commence_time"]
                    match["timestamp"] = datetime.fromisoformat(match["commence_time"].replace('Z', '+00:00')).timestamp()
                    home_logo_url, away_logo_url = build_team_logo_urls(
                        match.get("home_team"),
                        match.get("away_team"),
                    )
                    match["home_logo_url"] = home_logo_url
                    match["away_logo_url"] = away_logo_url

                    # ---- T29c: Elo per-request dedupe + reuse + stash for context ----
                    home_team_name = match.get("home_team")
                    away_team_name = match.get("away_team")

                    home_elo = None
                    away_elo = None
                    event_id = str(match.get("event_id") or match.get("id") or "")

                    if home_team_name and away_team_name:
                        try:
                            if elo_is_unhealthy() or elo_pair_attempts >= elo_budget:
                                home_elo = elo_cache_local.get(home_team_name)
                                away_elo = elo_cache_local.get(away_team_name)
                            else:
                                fresh_attempt = False

                                if home_team_name in elo_cache_local:
                                    home_elo = elo_cache_local[home_team_name]
                                else:
                                    cached_home = _elo_cache_get(home_team_name)
                                    if cached_home is not None:
                                        home_elo = cached_home
                                    else:
                                        fresh_attempt = True
                                        home_elo = get_team_elo(home_team_name)
                                        if home_elo is not None:
                                            _elo_cache_put(home_team_name, home_elo)
                                    elo_cache_local[home_team_name] = home_elo

                                if away_team_name in elo_cache_local:
                                    away_elo = elo_cache_local[away_team_name]
                                else:
                                    cached_away = _elo_cache_get(away_team_name)
                                    if cached_away is not None:
                                        away_elo = cached_away
                                    else:
                                        fresh_attempt = True
                                        away_elo = get_team_elo(away_team_name)
                                        if away_elo is not None:
                                            _elo_cache_put(away_team_name, away_elo)
                                    elo_cache_local[away_team_name] = away_elo

                                if fresh_attempt:
                                    elo_pair_attempts += 1

                            if home_elo is not None or away_elo is not None:
                                match["elo_home"] = home_elo
                                match["elo_away"] = away_elo
                                match["elo_ts"] = datetime.now(timezone.utc).isoformat()

                            if home_elo is not None and away_elo is not None:
                                if event_id:
                                    _match_elo_cache_put(event_id, home_elo, away_elo)
                                match["elo_predictions"] = calculate_elo_probabilities(home_elo, away_elo)
                        except Exception as elo_err:
                            logger.warning(
                                "Elo unavailable in /upcoming for %s vs %s: %s",
                                home_team_name,
                                away_team_name,
                                getattr(elo_err, "code", type(elo_err).__name__),
                            )
                            if home_team_name and home_team_name not in elo_cache_local:
                                elo_cache_local[home_team_name] = None
                            if away_team_name and away_team_name not in elo_cache_local:
                                elo_cache_local[away_team_name] = None
                            if elo_pair_attempts < elo_budget:
                                elo_pair_attempts += 1

                    # ---- end T29c block ----

                    # Add predictions in the expected format
                    match["predictions"] = {
                        "1x2": {
                            "prediction": predictions["prediction"],
                            "confidence": predictions["confidence"],
                            "probabilities": predictions["probabilities"],
                            "is_safe_bet": predictions["confidence"] >= 60,
                            "bookmaker_count": predictions["bookmaker_count"]
                        },
                        "best_odds": predictions["best_odds"],
                        "arbitrage": predictions["arbitrage"]
                    }

                logger.info("✅ Found %d matches from The Odds API", len(odds_matches))
                return make_ok({
                    "matches": odds_matches,
                    "total_matches": len(odds_matches),
                    "source": "The Odds API"
                })
        except APIError as e:
            logger.warning("⚠️  The Odds API unavailable: %s", e)
            return make_error(
                error=e,
                message="Failed to fetch upcoming matches",
                status_code=503
            )
        except Exception as e:
            logger.exception("⚠️  The Odds API error")
            return make_error(
                error="Unable to fetch matches. Please try again later.",
                message="Failed to fetch upcoming matches",
                status_code=500
            )

    except Exception as e:
        logger.exception("❌ Critical error")
        return make_error(
            error="Service temporarily unavailable. Please try again later.",
            message="Service temporarily unavailable",
            status_code=500
        )


@app.route("/search", methods=["POST"])
@legacy_endpoint
def search():
    """Search for matches by team name"""
    team_name = request.form.get("team_name", "").strip()

    if not team_name:
        return make_error(
            error="Please provide a team name",
            message="Invalid team name",
            status_code=400
        )

    try:
        logger.info("Handling /search request", extra={"team_name": team_name})
        logger.info("🔍 Searching for team: %s", team_name)

        # Use The Odds API to fetch matches from all leagues
        try:
            odds_matches = get_upcoming_matches_with_odds(
                league_codes=list(LEAGUE_CODE_MAPPING.keys()),
                next_n_days=30
            )
            
            if not odds_matches:
                # No matches from Odds API - return empty result
                logger.info("ℹ️ No matches available from The Odds API")
                return make_error(
                    error=f"No matches found for team '{team_name}' - try again later",
                    message="No matches available",
                    status_code=404
                )

            # Filter matches by team name
            team_name_lower = team_name.lower()
            filtered_matches = [
                match for match in odds_matches
                if team_name_lower in match.get("home_team", "").lower() or 
                   team_name_lower in match.get("away_team", "").lower()
            ]
            
            if not filtered_matches:
                return make_error(
                    error=f"No matches found for team '{team_name}'",
                    message="No matches found",
                    status_code=404
                )
            
            # Calculate predictions from odds for each match
            for match in filtered_matches:
                predictions = calculate_predictions_from_odds(match)

                # Format match data
                match["datetime"] = match["commence_time"]
                match["timestamp"] = datetime.fromisoformat(match["commence_time"].replace('Z', '+00:00')).timestamp()
                home_logo_url, away_logo_url = build_team_logo_urls(
                    match.get("home_team"),
                    match.get("away_team"),
                )
                match["home_logo_url"] = home_logo_url
                match["away_logo_url"] = away_logo_url

                # Add predictions in the expected format
                match["predictions"] = {
                    "1x2": {
                        "prediction": predictions["prediction"],
                        "confidence": predictions["confidence"],
                        "probabilities": predictions["probabilities"],
                        "is_safe_bet": predictions["confidence"] >= 60,
                        "bookmaker_count": predictions["bookmaker_count"]
                    },
                    "best_odds": predictions["best_odds"],
                    "arbitrage": predictions["arbitrage"]
                }
            
            # Sort by date
            filtered_matches = sorted(filtered_matches, key=lambda x: x["timestamp"])
            
            logger.info("✅ Found %d matches for '%s' from The Odds API", len(filtered_matches), team_name)
            return make_ok({
                "matches": filtered_matches,
                "source": "The Odds API"
            })

        except Exception as odds_e:
            logger.exception("⚠️ The Odds API error during search")
            return make_error(
                error="Search service temporarily unavailable",
                message="Search service temporarily unavailable",
                status_code=503
            )

    except Exception as e:
        logger.exception("Error in search")
        return make_error(
            error="Search failed. Please try again later.",
            message="Search failed",
            status_code=500
        )

@app.route("/match/<match_id>", methods=["GET"])
def get_match(match_id):
    """Get detailed information about a specific match"""
    logger.info("Handling /match request", extra={"match_id": match_id})
    # Endpoint deprecated - match details now come from The Odds API in /upcoming
    return make_error(
        error="Endpoint deprecated",
        message="This endpoint has been removed. Use documented routes instead.",
        status_code=410,
    )

@app.route("/predict/<match_id>", methods=["GET"])
def predict_match(match_id):
    logger.info("Handling /predict request", extra={"match_id": match_id})
    return make_error(
        error="Endpoint deprecated",
        message="This endpoint has been removed. Use documented routes instead.",
        status_code=410,
    )

@app.route("/match/<event_id>/totals", methods=["GET"])
def get_match_totals(event_id):
    """Get over/under predictions for a specific match on-demand"""
    try:
        with alias_logging_context():
            logger.info("Handling /match totals request", extra={"event_id": event_id})
            sport_key = request.args.get("sport_key")
            if not sport_key:
                return make_error(
                    error="sport_key parameter required",
                    message="Missing sport_key parameter",
                    status_code=400
                )

            from .odds_api_client import get_event_odds
            from .odds_calculator import calculate_totals_from_odds

            odds_data = get_event_odds(sport_key, event_id, regions="us,uk,eu", markets="totals")
            if not odds_data:
                return make_error(
                    error="No totals odds found for this match",
                    message="No totals odds found",
                    status_code=404
                )

            totals_predictions = calculate_totals_from_odds(odds_data)

            # Optional rolling xG context (internal-only fields)
            league_code = request.args.get("league")
            home_team = request.args.get("home_team")
            away_team = request.args.get("away_team")
            if league_code and home_team and away_team:
                _apply_recent_xg_context(home_team, away_team, league_code)

            payload = {
                "totals": totals_predictions,
                "source": "The Odds API"
            }

            # Attach rolling xG arrays via RequestMemo (internal fields only)
            memo = _get_request_memo()
            if league_code and home_team and away_team:
                _ensure_rolling_fields(memo, league_code, home_team, away_team, payload)

            return make_ok(payload)

    except Exception as e:
        logger.exception("Error fetching totals for %s", event_id)
        return make_error(
            error="Unable to load over/under data. Please try again later.",
            message="Failed to fetch totals",
            status_code=500
        )

@app.route("/match/<event_id>/btts", methods=["GET"])
def get_match_btts(event_id):
    """Get Both Teams To Score predictions for a specific match on-demand"""
    try:
        with alias_logging_context():
            logger.info("Handling /match btts request", extra={"event_id": event_id})

            mode = (request.args.get("mode") or "full").lower()
            if mode not in {"full", "market", "xg"}:
                return make_error(
                    error="Invalid mode",
                    message="mode must be one of full, market, or xg",
                    status_code=400,
                )

            want_market = mode in {"full", "market"}
            want_xg = mode in {"full", "xg"}
            if not want_market and not want_xg:
                return make_error(
                    error="Invalid mode",
                    message="mode must request at least one data source",
                    status_code=400,
                )

            sport_key = request.args.get("sport_key")
            home_team = request.args.get("home_team")
            away_team = request.args.get("away_team")
            league_code = request.args.get("league")

            if want_market and not sport_key:
                return make_error(
                    error="sport_key parameter required",
                    message="Missing sport_key parameter",
                    status_code=400,
                )

            from .odds_api_client import get_event_odds
            from .odds_calculator import calculate_btts_from_odds, calculate_btts_probability_from_xg

            btts_market = None
            if want_market:
                odds_data = get_event_odds(
                    sport_key,
                    event_id,
                    regions="us,uk,eu",
                    markets="btts",
                )
                if not odds_data:
                    return make_error(
                        error="No BTTS odds found for this match",
                        message="No BTTS odds found",
                        status_code=404,
                    )
                btts_market = calculate_btts_from_odds(odds_data)

            btts_xg = None
            rolling_payload: dict[str, Any] = {}
            if want_xg:
                home_snapshot: Optional[dict[str, Any]] = None
                away_snapshot: Optional[dict[str, Any]] = None

                if home_team and away_team and league_code:
                    home_snapshot, away_snapshot = _apply_recent_xg_context(
                        home_team, away_team, league_code
                    )
                    if home_snapshot is None:
                        home_snapshot = get_team_recent_xg_snapshot(home_team, league_code)
                    if away_snapshot is None:
                        away_snapshot = get_team_recent_xg_snapshot(away_team, league_code)

                def _avg(snapshot: Optional[dict[str, Any]], field: str) -> Optional[float]:
                    if not snapshot:
                        return None
                    wl = snapshot.get("window_len") or 0
                    if wl <= 0:
                        return None
                    try:
                        return float(snapshot.get(field, 0.0)) / wl
                    except (TypeError, ZeroDivisionError):
                        return None

                home_xg_per_game = _avg(home_snapshot, "xg_for_sum")
                away_xg_per_game = _avg(away_snapshot, "xg_for_sum")
                home_xga_per_game = _avg(home_snapshot, "xg_against_sum")
                away_xga_per_game = _avg(away_snapshot, "xg_against_sum")

                if home_team and away_team and league_code:
                    try:
                        memo = _get_request_memo()
                        resolved_home = resolve_team_name(home_team, provider="fbref")
                        resolved_away = resolve_team_name(away_team, provider="fbref")

                        xg_prediction = get_match_xg_prediction(
                            resolved_home, resolved_away, league_code, request_memo=memo
                        )

                        _ensure_rolling_fields(
                            memo, league_code, resolved_home, resolved_away, rolling_payload
                        )

                        if xg_prediction.get('available') and xg_prediction.get('xg'):
                            home_xg_per_game = home_xg_per_game or xg_prediction['xg'].get('home_stats', {}).get('xg_for_per_game')
                            away_xg_per_game = away_xg_per_game or xg_prediction['xg'].get('away_stats', {}).get('xg_for_per_game')

                        from .understat_client import fetch_understat_standings

                        current_season = get_current_season()
                        standings = fetch_understat_standings(league_code, current_season)
                        if standings:
                            home_lookup = resolved_home or home_team
                            away_lookup = resolved_away or away_team
                            home_st = next((t for t in standings if fuzzy_team_match(t['name'], home_lookup)), None)
                            away_st = next((t for t in standings if fuzzy_team_match(t['name'], away_lookup)), None)

                            if home_st and home_st.get('xGA') is not None and home_st.get('played', 0) > 0:
                                cand = home_st['xGA'] / home_st['played']
                                if home_xga_per_game is None:
                                    home_xga_per_game = cand
                            if away_st and away_st.get('xGA') is not None and away_st.get('played', 0) > 0:
                                cand = away_st['xGA'] / away_st['played']
                                if away_xga_per_game is None:
                                    away_xga_per_game = cand

                        if all(
                            v is not None
                            for v in [home_xg_per_game, away_xg_per_game, home_xga_per_game, away_xga_per_game]
                        ):
                            btts_xg = calculate_btts_probability_from_xg(
                                home_xg_per_game,
                                away_xg_per_game,
                                home_xga_per_game,
                                away_xga_per_game,
                            )

                    except Exception as e:
                        logger.warning("⚠️  Could not calculate xG-based BTTS: %s", e)
                        btts_xg = None

            btts_payload: dict[str, Any] = {}
            if want_market:
                btts_payload["market"] = btts_market
            if want_xg:
                btts_payload["xg_model"] = btts_xg

            response_payload = {
                "btts": btts_payload,
                "source": "The Odds API + xG Analysis",
            }
            if want_xg:
                response_payload.update(rolling_payload)

            return make_ok(response_payload)

    except Exception as e:
        logger.exception("Error fetching BTTS for %s", event_id)
        return make_error(
            error="Unable to load BTTS data. Please try again later.",
            message="Failed to fetch BTTS data",
            status_code=500
        )

@app.route("/match/<event_id>/xg", methods=["GET"])
def get_match_xg(event_id):
    """Get xG (Expected Goals) analysis for a specific match on-demand"""
    try:
        with alias_logging_context():
            logger.info("Handling /match xg request", extra={"event_id": event_id})
            home_team = request.args.get("home_team")
            away_team = request.args.get("away_team")
            league_code = request.args.get("league")

            if not home_team or not away_team:
                return make_error(
                    error="home_team and away_team parameters required",
                    message="Missing team parameters",
                    status_code=400
                )

            if not league_code:
                return make_error(
                    error="league parameter required",
                    message="Missing league parameter",
                    status_code=400
                )

            start_time = time.monotonic()

            # Use request memo and attach rolling arrays (internal fields)
            memo = _get_request_memo()
            xg_prediction = get_match_xg_prediction(
                home_team, away_team, league_code, request_memo=memo
            )

            if not xg_prediction.get('available'):
                elapsed_ms = (time.monotonic() - start_time) * 1000
                logger.info(
                    "context_xg ready in %.0f ms (partial)",
                    elapsed_ms,
                    extra={"event_id": event_id},
                )
                _apply_recent_xg_context(home_team, away_team, league_code)
                metadata = _normalize_xg_metadata(xg_prediction)
                # Even on partial, try to include rolling fields if memo had logs
                payload = {
                    "xg": None,
                    "error": xg_prediction.get('error', 'xG data not available'),
                    "source": "FBref via soccerdata",
                    **metadata,
                }
                _ensure_rolling_fields(memo, league_code, home_team, away_team, payload)
                return make_ok(payload)

            elapsed_ms = (time.monotonic() - start_time) * 1000
            logger.info(
                "context_xg ready in %.0f ms",
                elapsed_ms,
                extra={"event_id": event_id},
            )
            _apply_recent_xg_context(home_team, away_team, league_code)

            metadata = _normalize_xg_metadata(xg_prediction)
            payload = {
                "xg": xg_prediction,
                "source": "FBref via soccerdata",
                **metadata,
            }
            _ensure_rolling_fields(memo, league_code, home_team, away_team, payload)
            return make_ok(payload)

    except Exception as e:
        logger.exception("Error fetching xG for %s", event_id)
        return make_error(
            error="Unable to load xG data. Please try again later.",
            message="Failed to fetch xG data",
            status_code=200
        )

@app.route("/career_xg", methods=["GET"])
@legacy_endpoint
def get_career_xg():
    """Get career xG statistics (2010-2025) for a team"""
    try:
        logger.info("Handling /career_xg request")
        team = request.args.get("team")
        league = request.args.get("league")

        if not team or not league:
            return make_error(
                error="team and league parameters required",
                message="Missing team or league parameter",
                status_code=400
            )

        from .xg_data_fetcher import fetch_career_xg_stats

        career_stats = fetch_career_xg_stats(team, league)

        if not career_stats:
            return make_ok({
                "career_xg": None,
                "error": "No historical xG data available for this team",
                "source": "FBref (2010-2025)"
            })

        return make_ok({
            "career_xg": career_stats,
            "source": "FBref (2010-2025)"
        })

    except Exception as e:
        logger.exception("Error fetching career xG")
        return make_error(
            error="Unable to load career xG data",
            message="Failed to fetch career xG",
            status_code=200
        )


@app.route("/match/<event_id>/context_core", methods=["GET", "POST"])
def get_match_context_core(event_id):
    start_time = time.monotonic()
    try:
        logger.info("Handling /match context_core request", extra={"match_id": event_id})
        header_hint = _parse_header_elo_hint(request.headers.get("X-Elo-Hint"))
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            raw_league = payload.get("league")
            league, _lw = validate_league(raw_league)
            home_team, _ = validate_team_optional(payload.get("home_team"))
            away_team, _ = validate_team_optional(payload.get("away_team"))
            body_hint = payload.get("elo_hint") if isinstance(payload.get("elo_hint"), dict) else None
            elo_hint = _merge_elo_hints(header_hint, body_hint)
            effective_event_id = payload.get("event_id") or request.args.get("event_id") or event_id
        else:
            raw_league = request.args.get("league")
            league, _lw = validate_league(raw_league)
            home_team, _ = validate_team_optional(request.args.get("home_team"))
            away_team, _ = validate_team_optional(request.args.get("away_team"))
            elo_hint = header_hint
            effective_event_id = request.args.get("event_id") or event_id

        if not league:
            fallback_league = str(raw_league).strip().upper() if raw_league else ""
            if fallback_league:
                league = fallback_league
            else:
                return make_error(
                    error="league parameter required",
                    message="Missing league parameter",
                    status_code=400
                )

        try:
            context = _assemble_match_context_core(
                league,
                home_team,
                away_team,
                effective_event_id,
                elo_hint=elo_hint,
            )
        except APIError:
            raise
        except FuturesTimeoutError:
            raise
        except Exception:
            logger.exception("Error building core context for %s", event_id)
            payload = {
                "ok": True,
                "standings": {
                    "narrative": "Match context unavailable",
                    "has_data": False,
                    "home_team": None,
                    "away_team": None,
                },
                "elo": {
                    "home_rating": None,
                    "away_rating": None,
                    "predictions": None,
                },
                "meta": {
                    "league": league,
                    "home": home_team,
                    "away": away_team,
                },
            }
            elapsed_ms = (time.monotonic() - start_time) * 1000
            logger.info(
                "context_core ready in %.0f ms (error)",
                elapsed_ms,
                extra={"match_id": event_id},
            )
            return make_ok(payload)

        payload = {
            "ok": True,
            "standings": context,
            "elo": {
                "home_rating": (context.get("home_team") or {}).get("elo_rating"),
                "away_rating": (context.get("away_team") or {}).get("elo_rating"),
                "predictions": context.get("elo_predictions"),
            },
            "meta": {
                "league": league,
                "home": home_team,
                "away": away_team,
            },
        }

        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "context_core ready in %.0f ms",
            elapsed_ms,
            extra={"match_id": event_id},
        )
        return make_ok(payload)

    except APIError as e:
        logger.warning(
            "Upstream API error in /match/context_core: %s",
            getattr(e, "message", str(e)),
        )
        return make_error(
            {"source": getattr(e, "source", None), "detail": str(e)},
            "Upstream API error",
            status_code=502,
        )
    except FuturesTimeoutError:
        logger.warning("Global timeout in /match/context_core")
        return make_error(None, "Context assembly timeout", status_code=504)
    except Exception as e:
        logger.exception("Error in match context_core for %s", event_id)
        return make_error(
            error="Unable to load match context. Please try again later.",
            message="Failed to fetch match context",
            status_code=500,
        )


@app.route("/match/<match_id>/context", methods=["GET"])
def get_match_context(match_id):
    """Get match context including standings, form, and Elo ratings"""
    try:
        logger.info("Handling /match context request", extra={"match_id": match_id})
        raw_league = request.args.get("league")
        league, _lw = validate_league(raw_league)
        home_team, _ = validate_team_optional(request.args.get("home_team"))
        away_team, _ = validate_team_optional(request.args.get("away_team"))

        if not league:
            fallback_league = str(raw_league).strip().upper() if raw_league else ""
            if fallback_league:
                league = fallback_league
            else:
                return make_error(
                    error="league parameter required",
                    message="Missing league parameter",
                    status_code=400
                )

        event_id = request.args.get("event_id") or None

        try:
            context = _assemble_match_context_core(league, home_team, away_team, event_id)
        except APIError:
            raise
        except FuturesTimeoutError:
            raise
        except Exception as e:
            logger.exception("Error fetching context for %s", match_id)
            return make_ok({"narrative": "Match context unavailable"})

        return make_ok(context)

    except APIError as e:
        logger.warning(
            "Upstream API error in /match/context: %s",
            getattr(e, "message", str(e)),
        )
        return make_error(
            {"source": getattr(e, "source", None), "detail": str(e)},
            "Upstream API error",
            status_code=502,
        )
    except FuturesTimeoutError:
        logger.warning("Global timeout in /match/context")
        return make_error(None, "Context assembly timeout", status_code=504)
    except Exception as e:
        logger.exception("Error in match context for %s", match_id)
        return make_error(
            error="Unable to load match context. Please try again later.",
            message="Failed to fetch match context",
            status_code=500
        )

def generate_match_narrative(home_data, away_data):
    """Generate a narrative description of the match importance"""
    home_pos = home_data.get('position', 99)
    away_pos = away_data.get('position', 99)
    
    if home_pos <= 2 and away_pos <= 2:
        return "Top of the table clash between title contenders"
    elif home_pos <= 4 and away_pos <= 4:
        return "Champions League qualification battle"
    elif abs(home_pos - away_pos) <= 2:
        return "Close contest between neighboring teams in the standings"
    elif home_pos <= 3:
        return f"League leaders face mid-table opposition"
    elif away_pos <= 3:
        return f"Underdogs host league leaders"
    else:
        return "Mid-table encounter"

@app.route("/process_data", methods=["POST"])
def process_data():
    """Process all scraped match data"""
    logger.info("Handling /process_data request")
    return make_error(
        error="Endpoint deprecated",
        message="This endpoint has been removed. Use documented routes instead.",
        status_code=410,
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
