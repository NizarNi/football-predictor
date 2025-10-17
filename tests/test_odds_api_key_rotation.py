import os
from importlib import reload

from football_predictor import odds_api_client


def test_odds_api_key_rotation_includes_suffix(monkeypatch):
    # Clear any pre-existing Odds API key variables
    for key in list(os.environ):
        if key.startswith("ODDS_API_KEY"):
            monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("ODDS_API_KEY", "base-key")
    for idx in range(1, 9):
        monkeypatch.setenv(f"ODDS_API_KEY_{idx}", f"key-{idx}")

    reloaded_client = reload(odds_api_client)

    try:
        key_names = [entry.name for entry in reloaded_client.API_KEYS]
        assert key_names == [
            "ODDS_API_KEY",
            "ODDS_API_KEY_1",
            "ODDS_API_KEY_2",
            "ODDS_API_KEY_3",
            "ODDS_API_KEY_4",
            "ODDS_API_KEY_5",
            "ODDS_API_KEY_6",
            "ODDS_API_KEY_7",
            "ODDS_API_KEY_8",
        ]
        assert reloaded_client.API_KEYS[-1].value == "key-8"
    finally:
        monkeypatch.undo()
        reload(odds_api_client)


def test_refresh_reinstates_key_after_value_change(monkeypatch):
    for key in list(os.environ):
        if key.startswith("ODDS_API_KEY"):
            monkeypatch.delenv(key, raising=False)

    for idx in range(1, 9):
        monkeypatch.setenv(f"ODDS_API_KEY_{idx}", f"key-{idx}")

    reloaded_client = reload(odds_api_client)

    try:
        reloaded_client.invalid_keys["ODDS_API_KEY_8"] = "key-8"
        monkeypatch.setenv("ODDS_API_KEY_8", "key-8-new")

        reloaded_client.refresh_api_key_pool()

        key_names = [entry.name for entry in reloaded_client._get_valid_api_keys()]
        assert key_names[-1] == "ODDS_API_KEY_8"
        assert reloaded_client.API_KEYS[-1].value == "key-8-new"
    finally:
        monkeypatch.undo()
        reload(odds_api_client)
