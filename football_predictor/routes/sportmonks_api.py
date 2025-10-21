from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, jsonify

from .. import settings
from ..constants import SPORTMONKS_LEAGUE_IDS
from ..services.fotmob_feed import FeedService
from ..adapters.sportmonks import SportmonksAdapter
from ..adapters.sportmonks_odds import SportmonksOddsAdapter

bp = Blueprint("smonks_api", __name__, url_prefix="/api/smonks")
_service_singleton = None
_odds_service_singleton = None
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


def _get_odds_service():
    global _odds_service_singleton
    if _odds_service_singleton is None:
        _odds_service_singleton = FeedService(adapter=SportmonksOddsAdapter())
        log.info(
            "smonks_odds_feed service adapter=%s", type(_odds_service_singleton.adapter).__name__
        )
    return _odds_service_singleton


@bp.get("/feed")
def feed():
    direction = request.args.get("dir", "future")
    cursor = request.args.get("cursor")
    page_size_raw = request.args.get("page_size")

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

    srv = _get_service()
    log.info("smonks_feed comps=%s dir=%s cursor=%s", comp_codes, direction, cursor)
    payload = srv.load_page(direction=direction, cursor=cursor, page_size_raw=page_size_raw, comps=comp_codes)
    log.info(
        "smonks_feed items=%d window=%s",
        len(payload.get("items", [])),
        payload.get("_debug", {}).get("window"),
    )
    return jsonify(payload)


@bp.get("/odds-feed")
def odds_feed():
    direction = request.args.get("dir", "future")
    cursor = request.args.get("cursor")
    page_size_raw = request.args.get("page_size")

    default_codes = [c for c, lid in SPORTMONKS_LEAGUE_IDS.items() if lid]

    raw = (request.args.get("leagues") or "").strip().upper()
    if raw:
        wanted = []
        for tok in raw.split(","):
            code = tok.strip().upper()
            if SPORTMONKS_LEAGUE_IDS.get(code):
                wanted.append(code)
        comp_codes = wanted or default_codes
    else:
        comp_codes = default_codes

    srv = _get_odds_service()
    log.info(
        "smonks_odds_feed comps=%s dir=%s cursor=%s",
        comp_codes,
        direction,
        cursor,
    )
    payload = srv.load_page(
        direction=direction,
        cursor=cursor,
        page_size_raw=page_size_raw,
        comps=comp_codes,
    )
    log.info(
        "smonks_odds_feed items=%d window=%s",
        len(payload.get("items", [])),
        payload.get("_debug", {}).get("window"),
    )
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
