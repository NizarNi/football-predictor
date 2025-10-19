from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("fotmob_api", __name__, url_prefix="/api/fotmob")

_service_singleton = None


def _get_service():
    global _service_singleton
    if _service_singleton is None:
        from football_predictor.services.fotmob_feed import FeedService

        _service_singleton = FeedService()
    return _service_singleton


@bp.get("/feed")
def feed():
    cursor = request.args.get("cursor")
    direction = request.args.get("dir", "future")
    page_size = request.args.get("page_size", "25")
    srv = _get_service()
    payload = srv.load_page(direction=direction, cursor=cursor, page_size_raw=page_size)
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


@bp.get("/__debug_client")
def _debug_client():
    try:
        from football_predictor.compat import patch_asyncio_for_py311

        patch_asyncio_for_py311()
        from fotmob_api import FotMob

        c = FotMob()
        methods = [m for m in dir(c) if not m.startswith("_")]
        return {"ok": True, "methods": methods}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500
