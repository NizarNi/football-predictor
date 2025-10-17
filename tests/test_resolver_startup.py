import logging

import logging

import pytest

from football_predictor import name_resolver


@pytest.fixture(autouse=True)
def reset_resolver_state():
    name_resolver._reset_resolver_state_for_tests()
    yield
    name_resolver.warm_alias_resolver()


def test_resolver_startup_ready():
    providers = name_resolver.warm_alias_resolver()
    assert providers
    assert name_resolver.RESOLVER_READY_EVENT.is_set()
    assert name_resolver.await_resolver_ready(0.01)
    assert name_resolver.RESOLVER_READY is True


def test_resolver_seed_used_once(caplog):
    caplog.set_level(logging.WARNING, logger=name_resolver.logger.name)
    propagate_original = name_resolver.logger.propagate
    name_resolver.logger.propagate = True
    try:
        with name_resolver.alias_logging_context():
            _ = name_resolver.resolve_team_name("Arsenal", provider="fbref")
            assert name_resolver.resolver_seed_used() is True
    finally:
        name_resolver.logger.propagate = propagate_original
    assert name_resolver.get_seed_fallback_count() == 1

    seed_warnings = [rec for rec in caplog.records if "static alias seed" in rec.message]
    assert len(seed_warnings) == 1

    name_resolver.warm_alias_resolver()

    with name_resolver.alias_logging_context():
        _ = name_resolver.resolve_team_name("Arsenal", provider="fbref")
        assert name_resolver.resolver_seed_used() is False

    assert name_resolver.get_seed_fallback_count() == 1
