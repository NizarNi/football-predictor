from __future__ import annotations

from flask import Blueprint, request, jsonify

from ..constants import FOTMOB_COMP_CODES
from ..services.fotmob_feed import FeedService

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
    srv = _get_service()
    payload = srv.load_page(direction=direction, cursor=cursor, page_size_raw=page_size_raw, comps=FOTMOB_COMP_CODES)
    return jsonify(payload)


@bp.get("/match/<match_id>")
def match_stub(match_id: str):
    # Will fill in later phases with lineups/standings/events
    return jsonify({"match_id": str(match_id), "detail": "stub"})
