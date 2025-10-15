import os
import sys
import types

sys.modules.setdefault("soccerdata", types.ModuleType("soccerdata"))
sys.modules.setdefault("pandas", types.ModuleType("pandas"))

from football_predictor.app import app, build_team_logo_urls
from football_predictor.logo_resolver import resolve_logo, reset_logo_cache


def test_logo_url_pipeline_uses_static(tmp_path):
    static_root = app.static_folder
    logo_dir = os.path.join(static_root, "team_logos")
    os.makedirs(logo_dir, exist_ok=True)
    test_logo = os.path.join(logo_dir, "sunderland afc.png")
    with open(test_logo, "w") as f:
        f.write("png")

    reset_logo_cache()

    with app.test_request_context():
        home_logo_url, _ = build_team_logo_urls("Sunderland AFC", None)
        assert home_logo_url.startswith("/static/")
        assert "team_logos" in home_logo_url

    # Ensure resolver returns absolute path under static directory
    resolved_path = resolve_logo("Sunderland AFC")
    assert resolved_path.startswith(static_root)

    os.remove(test_logo)
