import os

from flask import Blueprint, abort, jsonify, render_template, request

from football_predictor.composition.providers import build_providers
from football_predictor.domain.contracts import (
    ILiveScoreProvider,
    IStandingsProvider,
    IXgProvider,
)

bp_fotmob = Blueprint("fotmob_explorer", __name__, url_prefix="/explore")


def _enabled() -> bool:
    return os.getenv("FOTMOB_EXPLORER_ENABLED", "false").lower() == "true"


@bp_fotmob.route("/fotmob", methods=["GET"])
def fotmob_page():
    if not _enabled():
        abort(404)
    # League defaults – use your existing canonical codes
    default_league = request.args.get("league", "PL")
    default_comp = request.args.get("competition", "CL")
    return render_template(
        "fotmob_explorer.html",
        default_league=default_league,
        default_competition=default_comp,
    )


@bp_fotmob.route("/api/fotmob/league_snapshot", methods=["GET"])
def api_league_snapshot():
    if not _enabled():
        return jsonify({"error": "disabled"}), 404
    league = request.args.get("league", "PL")
    prov = build_providers()
    xg: IXgProvider | None = getattr(prov, "xg", None)
    if xg is None or not hasattr(xg, "league_snapshot"):
        return jsonify({"error": "xg provider not available"}), 501
    data = xg.league_snapshot(league)
    return jsonify({"league": league, "snapshot": data})


@bp_fotmob.route("/api/fotmob/team", methods=["GET"])
def api_team():
    if not _enabled():
        return jsonify({"error": "disabled"}), 404
    league = request.args.get("league", "PL")
    team = request.args.get("team")
    if not team:
        return jsonify({"error": "missing team"}), 400
    prov = build_providers()
    xg: IXgProvider | None = getattr(prov, "xg", None)
    if xg is None or not hasattr(xg, "team_rolling_xg"):
        return jsonify({"error": "xg provider not available"}), 501
    data = xg.team_rolling_xg(league, team)
    return jsonify({"league": league, "team": team, "rolling": data})


@bp_fotmob.route("/api/fotmob/standings", methods=["GET"])
def api_standings():
    if not _enabled():
        return jsonify({"error": "disabled"}), 404
    comp = request.args.get("competition", "CL")
    prov = build_providers()
    sp: IStandingsProvider | None = getattr(prov, "standings", None)
    if sp is None or not hasattr(sp, "list_competition_standings"):
        return jsonify({"error": "standings provider not available"}), 501
    data = sp.list_competition_standings(comp)
    return jsonify({"competition": comp, "table": data})


@bp_fotmob.route("/api/fotmob/live", methods=["GET"])
def api_live():
    if not _enabled():
        return jsonify({"error": "disabled"}), 404
    comp = request.args.get("competition", "PL")
    prov = build_providers()
    lp: ILiveScoreProvider | None = getattr(prov, "live", None)
    if lp is None or not hasattr(lp, "live_events"):
        return jsonify({"error": "live provider not available"}), 501
    data = lp.live_events(comp)
    return jsonify({"competition": comp, "events": data})
