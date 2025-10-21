from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from flask import Blueprint, request, jsonify

from .. import settings
from ..constants import SPORTMONKS_LEAGUE_IDS
from ..services.fotmob_feed import FeedService
from ..adapters.sportmonks import SportmonksAdapter

bp = Blueprint("smonks_api", __name__, url_prefix="/api/smonks")
_service_singleton = None
log = logging.getLogger(__name__)


def _get_service():
    global _service_singleton
    if _service_singleton is None:
        # Force Sportmonks for this route regardless of global settings
        _service_singleton = FeedService(adapter=SportmonksAdapter())
        log.info(
            "smonks_feed service adapter=%s provider=%s",
            type(_service_singleton.adapter).__name__,
            settings.PROVIDER,
        )
    return _service_singleton


@bp.get("/feed")
def feed():
    direction = request.args.get("dir", "future")
    cursor = request.args.get("cursor")
    page_size_raw = request.args.get("page_size")
    limit_raw = request.args.get("limit")
    if limit_raw is not None:
        page_size_raw = limit_raw

    # Default leagues = Top-5 (those that have a Sportmonks ID)
    default_codes = [c for c, lid in SPORTMONKS_LEAGUE_IDS.items() if lid]

    raw = (request.args.get("leagues") or "").strip().upper()

    if raw:
        wanted = []
        for tok in raw.split(","):
            code = tok.strip().upper()
            # Accept only codes present in SPORTMONKS_LEAGUE_IDS AND mapped to a league id
            if SPORTMONKS_LEAGUE_IDS.get(code):
                wanted.append(code)
        comp_codes = wanted or default_codes
    else:
        comp_codes = default_codes

    include_logos = _parse_bool(request.args.get("include_logos"), True)

    srv = _get_service()
    log.info(
        "smonks_feed comps=%s dir=%s cursor=%s include_logos=%s",
        comp_codes,
        direction,
        cursor,
        include_logos,
    )
    payload = srv.load_page(
        direction=direction,
        cursor=cursor,
        page_size_raw=page_size_raw,
        comps=comp_codes,
        include_logos=include_logos,
    )
    log.info(
        "smonks_feed items=%d window=%s",
        len(payload.get("items", [])),
        payload.get("_debug", {}).get("window"),
    )
    items = payload.get("items") or []
    payload["items"] = [_format_feed_item(item, include_logos=include_logos) for item in items]
    return jsonify(payload)


@bp.get("/match/<match_id>")
def match_stub(match_id: str):
    # Will fill in later phases with lineups/standings/events
    return jsonify({"match_id": str(match_id), "detail": "stub"})


@bp.get("/health")
def health():
    """
    Lightweight diagnostics:
      - verifies SPORTMONKS_KEY is present
      - probes league visibility for Top-5
      - counts fixtures per league in the current 90d window
    """

    key_loaded = bool(settings.SPORTMONKS_KEY)
    base = settings.SPORTMONKS_BASE
    leagues = [c for c, lid in SPORTMONKS_LEAGUE_IDS.items() if lid]

    adapter = SportmonksAdapter(timeout_ms=settings.SPORTMONKS_TIMEOUT_MS)

    visibility = {}
    for code in leagues:
        lid = SPORTMONKS_LEAGUE_IDS.get(code)
        try:
            ok = adapter.probe_league(int(lid)) if lid else False
        except Exception:
            ok = False
        visibility[code] = bool(ok)

    now = datetime.now(timezone.utc)
    start_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = (now + timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    counts = {}
    for code in leagues:
        try:
            items = adapter.get_fixtures(code, start_iso, end_iso)
            counts[code] = len(items or [])
        except Exception as exc:  # pragma: no cover - network dependent
            counts[code] = f"error:{type(exc).__name__}"

    return jsonify(
        {
            "sportmonks_base": base,
            "sportmonks_key_loaded": key_loaded,
            "league_visibility": visibility,
            "fixture_counts_90d": counts,
        }
    )
def _parse_bool(value: Optional[str], default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _sanitize_logo(value: Any, include_logos: bool) -> Optional[str]:
    if not include_logos:
        return None
    if isinstance(value, str) and value.strip():
        return value
    return None


def _format_feed_item(item: Dict[str, Any], include_logos: bool = True) -> Dict[str, Any]:
    fixture_id = _safe_int(item.get("fixture_id"))
    if fixture_id is None:
        fixture_id = _safe_int(item.get("match_id"))

    league_id = _safe_int(item.get("league_id"))
    season_id = _safe_int(item.get("season_id"))
    kickoff = item.get("kickoff_utc") or item.get("kickoff_iso")
    if isinstance(kickoff, datetime):
        kickoff = kickoff.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    kickoff_str = kickoff if isinstance(kickoff, str) else None

    status = item.get("status") or "NS"
    round_name = item.get("round")

    venue = item.get("venue") or {}
    venue_name = venue.get("name") if isinstance(venue, dict) else None
    venue_city = venue.get("city") if isinstance(venue, dict) else None

    home_raw = item.get("home") or {}
    away_raw = item.get("away") or {}

    home_team = {
        "id": _safe_int(home_raw.get("id")),
        "name": home_raw.get("display_name") or home_raw.get("name"),
        "logo": _sanitize_logo(home_raw.get("logo"), include_logos),
    }
    away_team = {
        "id": _safe_int(away_raw.get("id")),
        "name": away_raw.get("display_name") or away_raw.get("name"),
        "logo": _sanitize_logo(away_raw.get("logo"), include_logos),
    }

    tv_stations_raw = item.get("tv_stations") or []
    tv_stations = [str(station) for station in tv_stations_raw if isinstance(station, str) and station.strip()]

    referee = item.get("referee")
    if not isinstance(referee, str) or not referee.strip():
        referee = None

    formatted: Dict[str, Any] = {
        "fixture_id": fixture_id,
        "league_id": league_id,
        "season_id": season_id,
        "kickoff_utc": kickoff_str,
        "status": status,
        "round": round_name,
        "venue": {"name": venue_name, "city": venue_city},
        "home_team": home_team,
        "away_team": away_team,
    }
    if tv_stations:
        formatted["tv_stations"] = tv_stations
    if referee:
        formatted["referee"] = referee
    return formatted
