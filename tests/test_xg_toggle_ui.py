def render_xg_toggle_html(data):
    """Simulate the HTML snippet rendered for the xG toggle block."""

    status = (data or {}).get("refresh_status")
    hint_active = status in {"warming", "debounced"}
    hint_class = "small text-muted mt-2" + ("" if hint_active else " d-none")
    hint_text = "Warming detailed match logs… cooldown active." if hint_active else ""
    panel_class = "collapse show" if status == "ready" else "collapse"
    panel_shell = (
        f'<div id="xg-state-card" class="alert alert-warning xg-state-card d-none"></div>'
        '<div id="xg-snapshot" class="mt-3"></div>'
        '<div id="xg-analysis" class="mt-3">'
        '<div id="home-xg-chart-holder" class="mb-3"></div>'
        '<div id="away-xg-chart-holder" class="mb-3"></div>'
        '</div>'
    )

    return (
        '<div id="xg-toggle-container" class="mb-3">'
        '<button id="xg-toggle" class="btn btn-outline-secondary btn-sm">Show xG details</button>'
        f'<div id="xg-hint" class="{hint_class}">{hint_text}</div>'
        '</div>'
        f'<div id="xg-details-panel" class="{panel_class}">{panel_shell}</div>'
    )


def test_xg_toggle_snapshot_renders():
    data = {"fast_path": True, "completeness": "season_only", "refresh_status": "warming"}
    html = render_xg_toggle_html(data)
    assert "Show xG details" in html
    assert "Warming detailed match logs" in html
    assert 'id="xg-state-card"' in html


def test_xg_toggle_ready_state():
    data = {"fast_path": True, "completeness": "season_plus_rolling", "refresh_status": "ready"}
    html = render_xg_toggle_html(data)
    assert "Show xG details" in html
    assert "Warming" not in html
    assert 'collapse show' in html
