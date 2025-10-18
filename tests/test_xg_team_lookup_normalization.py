import logging

import pytest

from football_predictor import xg_data_fetcher


class DummyResolver:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls: list[str] = []

    def normalize(self, raw, provider="fbref"):
        self.calls.append(raw)
        return self.mapping.get(raw, raw)


@pytest.fixture(autouse=True)
def clear_xg_index():
    xg_data_fetcher._xg_team_index.clear()
    yield
    xg_data_fetcher._xg_team_index.clear()


def test_find_team_xg_alias_resolution(caplog):
    league_xg = {
        "US Lecce": {"team": "US Lecce", "xg": 1.0},
        "US Sassuolo": {"team": "US Sassuolo", "xg": 2.0},
        "SV Werder Bremen": {"team": "SV Werder Bremen", "xg": 3.0},
        "1. FC Heidenheim": {"team": "1. FC Heidenheim", "xg": 4.0},
    }
    resolver = DummyResolver(
        {
            "US Lecce": "US Lecce",
            "Lecce": "US Lecce",
            "US Sassuolo": "US Sassuolo",
            "Sassuolo": "US Sassuolo",
            "SV Werder Bremen": "SV Werder Bremen",
            "Werder Bremen": "SV Werder Bremen",
            "1. FC Heidenheim": "1. FC Heidenheim",
            "Heidenheim": "1. FC Heidenheim",
        }
    )

    original_propagate = xg_data_fetcher.logger.propagate
    xg_data_fetcher.logger.propagate = True
    try:
        caplog.set_level(logging.INFO, logger=xg_data_fetcher.logger.name)

        result_lecce = xg_data_fetcher._find_team_xg(
            "SA", "2023", "Lecce", league_xg, resolver
        )
        assert result_lecce is league_xg["US Lecce"]

        result_sassuolo = xg_data_fetcher._find_team_xg(
            "SA", "2023", "Sassuolo", league_xg, resolver
        )
        assert result_sassuolo is league_xg["US Sassuolo"]

        result_werder = xg_data_fetcher._find_team_xg(
            "BL1", "2023", "Werder Bremen", league_xg, resolver
        )
        assert result_werder is league_xg["SV Werder Bremen"]

        result_heidenheim = xg_data_fetcher._find_team_xg(
            "BL1", "2023", "Heidenheim", league_xg, resolver
        )
        assert result_heidenheim is league_xg["1. FC Heidenheim"]

        build_logs = [
            record
            for record in caplog.records
            if "xg_index: built canonical map" in record.message
        ]
        assert len(build_logs) == 2

        # Subsequent lookup should reuse cached index without new log entry
        caplog.clear()
        repeated = xg_data_fetcher._find_team_xg(
            "SA", "2023", "Lecce", league_xg, resolver
        )
        assert repeated is league_xg["US Lecce"]
        build_logs_repeat = [
            record
            for record in caplog.records
            if "xg_index: built canonical map" in record.message
        ]
        assert not build_logs_repeat
    finally:
        xg_data_fetcher.logger.propagate = original_propagate
