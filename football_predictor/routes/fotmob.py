from flask import Blueprint, render_template

bp = Blueprint("fotmob_page", __name__, url_prefix="/fotmob")


@bp.get("/")
def index():
    return render_template("fotmob/index.html")
