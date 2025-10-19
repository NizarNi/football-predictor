from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("fotmob_api", __name__, url_prefix="/api/fotmob")


@bp.get("/feed")
def feed():
    """Return a stubbed FotMob feed response."""
    # Cursor-based feed will be implemented in T3.3
    cursor = request.args.get("cursor")
    direction = request.args.get("dir", "future")
    page_size = request.args.get("page_size", "25")
    return jsonify(
        {
            "items": [],
            "next_cursor": None,
            "prev_cursor": None,
            "has_more_future": False,
            "has_more_past": False,
            "_debug": {
                "cursor": cursor,
                "dir": direction,
                "page_size": page_size,
                "note": "stub; implemented in T3.3",
            },
        }
    )


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
