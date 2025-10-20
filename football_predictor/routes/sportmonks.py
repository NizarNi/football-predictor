from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("smonks_page", __name__, url_prefix="/sportmonks")


@bp.get("/")
def index():
    # Reuse feed template structure; copy the fotmob template if needed
    return render_template("sportmonks/index.html")
