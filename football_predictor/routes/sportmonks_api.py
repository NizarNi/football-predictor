from __future__ import annotations

import logging

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
        # Force Sportmonks for this route regardless of settings.PROVIDER
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


@bp.get("/match/<match_id>")
def match_stub(match_id: str):
    # Will fill in later phases with lineups/standings/events
    return jsonify({"match_id": str(match_id), "detail": "stub"})
