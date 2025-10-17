import logging
import time

from football_predictor import name_resolver


def test_duplicate_alias_logs_suppressed(caplog):
    name_resolver._reset_alias_log_throttle_for_tests(interval=0.01)
    caplog.set_level(logging.DEBUG, logger=name_resolver.logger.name)
    propagate_original = name_resolver.logger.propagate
    name_resolver.logger.propagate = True

    try:
        with caplog.at_level(logging.DEBUG, logger=name_resolver.logger.name):
            with name_resolver.alias_logging_context():
                name_resolver.resolve_team_name("Man United", provider="fbref")
                name_resolver.resolve_team_name("Man United", provider="fbref")
                name_resolver.resolve_team_name("Man United", provider="fbref")

            time.sleep(0.02)
            name_resolver._flush_alias_suppressed(force=True)
    finally:
        name_resolver.logger.propagate = propagate_original

    debug_logs = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.DEBUG and "alias" in record.getMessage()
    ]
    info_logs = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.INFO and "suppressed" in record.getMessage()
    ]

    assert len(debug_logs) == 1
    assert any("duplicate mappings" in msg for msg in info_logs)

    name_resolver._reset_alias_log_throttle_for_tests()
