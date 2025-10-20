from __future__ import annotations

from flask import Blueprint, request, jsonify

from ..constants import SPORTMONKS_LEAGUE_IDS
from ..services.fotmob_feed import FeedService
from ..validators import validate_fotmob_comp

bp = Blueprint("smonks_api", __name__, url_prefix="/api/smonks")
_service_singleton = None


def _get_service():
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = FeedService()
    return _service_singleton


@bp.get("/feed")
def feed():
    direction = request.args.get("dir", "future")
    cursor = request.args.get("cursor")
    page_size_raw = request.args.get("page_size")

    # Default leagues = Top-5 (those that have a Sportmonks ID)
    default_codes = [c for c, lid in SPORTMONKS_LEAGUE_IDS.items() if lid]

    # Optional override via ?leagues=EPL,BUNDES
    raw = (request.args.get("leagues") or "").strip()
    if raw:
        wanted = []
        for tok in raw.split(","):
            try:
                code = validate_fotmob_comp(tok)
            except Exception:
                continue
            if SPORTMONKS_LEAGUE_IDS.get(code):
                wanted.append(code)
        comp_codes = wanted or default_codes
    else:
        comp_codes = default_codes

    srv = _get_service()
    payload = srv.load_page(direction=direction, cursor=cursor, page_size_raw=page_size_raw, comps=comp_codes)
    return jsonify(payload)


@bp.get("/match/<match_id>")
def match_stub(match_id: str):
    # Will fill in later phases with lineups/standings/events
    return jsonify({"match_id": str(match_id), "detail": "stub"})
