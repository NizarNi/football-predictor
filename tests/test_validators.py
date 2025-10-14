import pytest

from football_predictor.constants import DEFAULT_NEXT_N_DAYS
from football_predictor.validators import (
    validate_league,
    validate_next_days,
    validate_team,
)


def test_validate_league_normalizes_and_accepts_known_code():
    assert validate_league("pl") == "PL"


def test_validate_league_rejects_unknown_code():
    with pytest.raises(ValueError, match="Unsupported league code"):
        validate_league("XYZ")


def test_validate_league_required():
    with pytest.raises(ValueError, match="league is required"):
        validate_league(None, required=True)


def test_validate_team_rejects_empty_when_required():
    with pytest.raises(ValueError, match="team name is required"):
        validate_team("   ", required=True, field_name="team_name")


def test_validate_team_rejects_numeric_or_special_characters():
    with pytest.raises(ValueError, match="Invalid team name"):
        validate_team("12345", required=True, field_name="team name")
    with pytest.raises(ValueError, match="Invalid team name"):
        validate_team("Team!", required=True, field_name="team name")


def test_validate_team_returns_normalized_value():
    assert validate_team("  Paris Saint-Germain  ", required=True, field_name="team name") == "Paris Saint-Germain"


def test_validate_next_days_defaults_when_missing():
    assert validate_next_days(None) == DEFAULT_NEXT_N_DAYS
    assert validate_next_days("   ") == DEFAULT_NEXT_N_DAYS


def test_validate_next_days_enforces_range_and_type():
    assert validate_next_days("7") == 7
    assert validate_next_days(90) == 90
    with pytest.raises(ValueError, match="integer"):
        validate_next_days("abc")
    with pytest.raises(ValueError, match="between 1 and 90"):
        validate_next_days(0)
    with pytest.raises(ValueError, match="between 1 and 90"):
        validate_next_days(120)
