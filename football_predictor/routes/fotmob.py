from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("fotmob_page", __name__, url_prefix="/fotmob")


@bp.get("/")
def index() -> str:
    """Render the FotMob feed page."""
    return render_template("fotmob/index.html")
