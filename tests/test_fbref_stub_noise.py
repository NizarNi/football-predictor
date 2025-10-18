import logging

from football_predictor import xg_data_fetcher


class StubFBrefNoSchedule:
    """Stub FBref client lacking read_schedule for warm-up scenarios."""


class StubFBrefRaises:
    def read_schedule(self, league_code, team_name, season):
        raise RuntimeError("simulated FBref transient")


def test_skip_placeholder_teams(caplog):
    logger = logging.getLogger("football_predictor.xg_data_fetcher")
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            out = xg_data_fetcher.fetch_team_match_logs(
                "Home",
                "PL",
                season=2025,
                fbref_client=StubFBrefNoSchedule(),
            )
    finally:
        logger.removeHandler(caplog.handler)

    assert out == []
    assert any("Skipping placeholder team" in record.message for record in caplog.records)


def test_guard_missing_read_schedule(caplog):
    logger = logging.getLogger("football_predictor.xg_data_fetcher")
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            out = xg_data_fetcher.fetch_team_match_logs(
                "Chelsea",
                "PL",
                season=2025,
                fbref_client=StubFBrefNoSchedule(),
            )
    finally:
        logger.removeHandler(caplog.handler)

    assert out == []
    assert any("lacks 'read_schedule'" in record.message for record in caplog.records)


def test_downgrade_to_debug_on_exception(caplog):
    logger = logging.getLogger("football_predictor.xg_data_fetcher")
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            out = xg_data_fetcher.fetch_team_match_logs(
                "Chelsea",
                "PL",
                season=2025,
                fbref_client=StubFBrefRaises(),
            )
    finally:
        logger.removeHandler(caplog.handler)

    assert out == []
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    assert any("non-fatal" in record.message for record in caplog.records)
