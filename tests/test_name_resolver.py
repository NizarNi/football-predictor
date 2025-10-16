"""Tests for the team name resolver helper."""

from football_predictor.name_resolver import resolve_team_name


def test_fbref_exact_and_aliases():
    names = [
        "Wolverhampton Wanderers",
        "Wolves",
        "Wolverhampton",
    ]
    for name in names:
        assert (
            resolve_team_name(name, provider="fbref")
            == "Wolverhampton Wanderers"
        )


def test_fbref_nott_ham_forest():
    names = ["Nott'ham Forest", "Nottingham Forest", "Forest"]
    for name in names:
        assert (
            resolve_team_name(name, provider="fbref")
            == "Nottingham Forest"
        )


def test_fbref_brighton():
    names = [
        "Brighton and Hove Albion",
        "Brighton & Hove Albion",
        "Brighton",
    ]
    for name in names:
        assert (
            resolve_team_name(name, provider="fbref")
            == "Brighton & Hove Albion"
        )


def test_fbref_koln():
    names = ["Koln", "Köln", "FC Koln", "1. FC Köln"]
    for name in names:
        assert resolve_team_name(name, provider="fbref") == "Köln"
