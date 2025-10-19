from __future__ import annotations

from datetime import datetime, timedelta, timezone
from flask import Blueprint, jsonify, request
from ..services.fotmob_feed import FeedService

bp = Blueprint("fotmob_api", __name__, url_prefix="/api/fotmob")

_service_singleton = None


def _get_service():
    global _service_singleton
    if _service_singleton is None:
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


@bp.get("/__debug_snapshot")
def debug_snapshot():
    """Return counts per competition over a wide window (past 7d .. next 7d)."""
    from ..constants import FOTMOB_COMP_CODES
    from ..adapters.fotmob import FotMobAdapter

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ad = FotMobAdapter()
    out = {}
    for code in FOTMOB_COMP_CODES:
        try:
            items = ad.get_fixtures(code, start, end)
            out[code] = {"count": len(items), "sample": (items[:2] if items else [])}
        except Exception as e:
            out[code] = {"error": str(e)}
    return jsonify({"window": [start, end], "per_comp": out})


@bp.get("/__probe_day")
def probe_day():
    """
    Fetch raw FotMob fallback for a given date (YYYY-MM-DD) and return tournament id histogram.
    """
    import requests

    date = request.args.get("date")
    if not date:
        return jsonify({"error": "use ?date=YYYY-MM-DD"}), 400
    try:
        dt = datetime.fromisoformat(date)
    except Exception:
        return jsonify({"error": "bad date"}), 400

    # Use the same fallback endpoint as adapter
    url = "https://www.fotmob.com/api/matches"
    params = {"date": dt.strftime("%Y%m%d"), "ccode": "ENG"}
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.fotmob.com/",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return jsonify({"date": date, "http_error": str(e)}), 502

    # Walk and collect tournament ids
    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                if isinstance(v, (dict, list)):
                    yield from walk(v)

    tids = {}
    samples = []
    for m in walk(data):
        if not isinstance(m, dict):
            continue
        tid = (
            m.get("tournamentId")
            or (m.get("tournament") or {}).get("id")
            or (m.get("league") or {}).get("id")
            or (m.get("competition") or {}).get("id")
        )
        if tid is None:
            continue
        try:
            tid = int(tid)
        except Exception:
            continue
        tids[tid] = tids.get(tid, 0) + 1
        if len(samples) < 3:
            samples.append(
                {k: m.get(k) for k in ("id", "matchId", "time", "date", "status", "tournamentId")}
            )

    return jsonify({"date": date, "tournament_counts": tids, "samples": samples})
