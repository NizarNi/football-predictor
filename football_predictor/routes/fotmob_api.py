from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..services.fotmob_feed import FeedService

bp = Blueprint("fotmob_api", __name__, url_prefix="/api/fotmob")


_service = FeedService()


@bp.get("/feed")
def feed():
    cursor = request.args.get("cursor")
    direction = request.args.get("dir", "future")
    page_size = request.args.get("page_size", "25")
    payload = _service.load_page(direction=direction, cursor=cursor, page_size_raw=page_size)
    return jsonify(payload)


@bp.get("/match/<match_id>")
def match(match_id: str):
    """Return a stubbed FotMob match response."""
    # Detailed match JSON will be implemented in T4.x
    return jsonify(
        {
            "match_id": str(match_id),
            "status": "stub",
            "note": "detailed match data will be implemented in T4.x",
        }
    )
