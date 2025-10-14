import pytest

from football_predictor.utils import get_team_logo, TEAM_LOGO_OVERRIDES


class _FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


def _patch_head(monkeypatch, status_code=200):
    def fake_head(url, allow_redirects=True, timeout=0.5):
        fake_head.called_with = url  # type: ignore[attr-defined]
        return _FakeResponse(status_code=status_code)

    fake_head.called_with = None  # type: ignore[attr-defined]
    monkeypatch.setattr("football_predictor.utils.requests.head", fake_head)
    return fake_head


def test_team_logo_uses_override(monkeypatch):
    fake_head = _patch_head(monkeypatch)

    logo_url = get_team_logo("Spurs", "PL")

    assert "Tottenham%20Hotspur" in logo_url
    assert fake_head.called_with is not None


def test_team_logo_returns_default_on_404(monkeypatch, caplog):
    _patch_head(monkeypatch, status_code=404)

    with caplog.at_level("WARNING"):
        logo_url = get_team_logo("Unknown Club", "PL")

    assert logo_url == TEAM_LOGO_OVERRIDES["default"]
    assert any("Logo missing" in message for message in caplog.messages)


def test_team_logo_handles_missing_team(monkeypatch, caplog):
    _patch_head(monkeypatch)

    with caplog.at_level("WARNING"):
        logo_url = get_team_logo(None, "PL")

    assert logo_url == TEAM_LOGO_OVERRIDES["default"]
    assert any("Missing team name" in message for message in caplog.messages)
