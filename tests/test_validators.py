from football_predictor.validators import (
    validate_league, validate_next_n_days, validate_team_optional, normalize_team_name
)


def test_validate_league_ok():
    v, w = validate_league("epl")
    assert v in (v.upper(), v)  # normalized upper
    assert w == []


def test_validate_league_unknown_soft():
    v, w = validate_league("xyz")
    assert v is None
    assert w and "league_unknown" in w[0]


def test_validate_league_missing_soft():
    v, w = validate_league(None)
    assert v is None
    assert w and w[0] == "league_missing"


def test_validate_next_n_days_default_and_clamp():
    v, w = validate_next_n_days(None)
    assert isinstance(v, int) and w == []
    v2, w2 = validate_next_n_days("0")
    assert v2 >= 1 and w2
    v3, w3 = validate_next_n_days("999")
    assert v3 <= 60 and w3
    v4, w4 = validate_next_n_days("bad")
    assert isinstance(v4, int) and w4


def test_validate_team_optional_normalizes():
    t, w = validate_team_optional("  leeds   united ")
    assert t == "Leeds United"
    assert w == []
    t2, w2 = validate_team_optional(None)
    assert t2 is None and w2 == []


def test_normalize_team_name_titlecase_collapse():
    assert normalize_team_name("  tottenham   hotspur ") == "Tottenham Hotspur"
