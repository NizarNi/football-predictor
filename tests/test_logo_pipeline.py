import os
import sys
import types

import pytest
import requests

sys.modules.setdefault("soccerdata", types.ModuleType("soccerdata"))
sys.modules.setdefault("pandas", types.ModuleType("pandas"))

from football_predictor.app import app, build_team_logo_urls
from football_predictor.logo_resolver import FALLBACK, resolve_logo, reset_logo_cache


class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


def make_tree_entry(path: str) -> dict:
    return {"path": path, "type": "blob"}


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_logo_cache()
    yield
    reset_logo_cache()


def test_logo_pipeline_prefers_github(monkeypatch):
    from football_predictor import github_logo_index

    def fake_get(url, headers=None, timeout=None):
        return DummyResponse(
            {
                "tree": [
                    make_tree_entry("logos/england/premier-league/sunderland-afc.svg"),
                    make_tree_entry("logos/england/premier-league/leeds-united.png"),
                ]
            }
        )

    monkeypatch.setattr(github_logo_index.requests, "get", fake_get)

    with app.test_request_context():
        home_logo_url, away_logo_url = build_team_logo_urls("Sunderland AFC", None)

    assert home_logo_url.endswith("sunderland-afc.svg")
    assert home_logo_url.startswith(github_logo_index.RAW_BASE)
    assert away_logo_url.startswith("/static/")

    resolved = resolve_logo("Leeds United")
    assert resolved.endswith("leeds-united.png")
    assert resolved.startswith(github_logo_index.RAW_BASE)


def test_logo_pipeline_falls_back_on_failure(monkeypatch):
    from football_predictor import github_logo_index

    def fake_get(url, headers=None, timeout=None):
        raise github_logo_index.requests.RequestException("boom")

    monkeypatch.setattr(github_logo_index.requests, "get", fake_get)

    result = resolve_logo("Imaginary Club")
    assert os.path.samefile(result, FALLBACK)

    with app.test_request_context():
        home_logo_url, away_logo_url = build_team_logo_urls("Imaginary Club", "Other")

    assert home_logo_url.endswith("generic_shield.svg")
    assert away_logo_url.endswith("generic_shield.svg")
    assert home_logo_url.startswith("/static/")
