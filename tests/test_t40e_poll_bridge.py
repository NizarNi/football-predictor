from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "football_predictor" / "templates" / "index.html"


def test_poll_bridge_function_present():
    html = TEMPLATE_PATH.read_text()
    assert "async function pollForXgReady" in html
    assert "xG data ready, re-rendering charts" in html
    assert "xG polling timeout reached; no update" in html


def test_poll_bridge_triggers_after_warming():
    html = TEMPLATE_PATH.read_text()
    assert "setTimeout(() => pollForXgReady(currentMatchData.id), 3000);" in html


def test_poll_bridge_status_messages():
    html = TEMPLATE_PATH.read_text()
    assert "statusEl.textContent = 'xG ready.'" in html
    assert "statusEl.textContent = 'xG unavailable.'" in html
    assert "statusEl.textContent = 'Warming detailed match logs… (cooldown active)'" in html
