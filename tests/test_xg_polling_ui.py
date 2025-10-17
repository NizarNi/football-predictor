from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "football_predictor" / "templates" / "index.html"


def test_xg_polling_timeout_copy_present():
    html = TEMPLATE_PATH.read_text()
    assert "xG data not ready in time. Try again shortly." in html


def test_xg_polling_shell_contains_state_card():
    html = TEMPLATE_PATH.read_text()
    assert 'id="xg-state-card"' in html
    assert 'id="xg-hint"' in html
    assert 'id="home-xg-chart-holder"' in html
