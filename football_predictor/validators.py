"""Input validation helpers for request parameters."""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from .constants import DEFAULT_NEXT_N_DAYS, LEAGUE_CODE_MAPPING

logger = logging.getLogger(__name__)

_TEAM_PATTERN = re.compile(r"^[A-Za-z .&'()-]+$")

_LEAGUE_ALIASES = {
    "EPL": "PL",
    "ENGLISH PREMIER LEAGUE": "PL",
    "PREMIER LEAGUE": "PL",
    "LA LIGA": "PD",
    "SPANISH LA LIGA": "PD",
    "LALIGA": "PD",
    "BUNDESLIGA": "BL1",
    "GERMAN BUNDESLIGA": "BL1",
    "SERIE A": "SA",
    "ITALIAN SERIE A": "SA",
    "LIGUE 1": "FL1",
    "FRENCH LIGUE 1": "FL1",
    "UEFA CHAMPIONS LEAGUE": "CL",
    "UEFA EUROPA LEAGUE": "EL",
}


def _normalize(value: Optional[str]) -> Optional[str]:
    """Strip whitespace and return ``None`` for empty strings."""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _log_and_raise(param_name: str, message: str) -> None:
    """Log a validation failure and raise ``ValueError``."""
    logger.warning("Validation failed for %s: %s", param_name, message)
    raise ValueError(message)


def validate_league(league: Optional[str], *, required: bool = False) -> Optional[str]:
    """Validate and normalize a league code.

    Parameters
    ----------
    league:
        The league code provided by the client. ``None`` is allowed when
        ``required`` is ``False``.
    required:
        When ``True``, ``league`` must be provided.

    Returns
    -------
    Optional[str]
        Normalized league code or ``None`` when not required.

    Raises
    ------
    ValueError
        If the value is missing (and required) or not part of the supported
        mapping.
    """

    normalized = _normalize(league)

    if normalized is None:
        if required:
            _log_and_raise("league", "league is required")
        return None

    league_code = normalized.upper()
    league_code = _LEAGUE_ALIASES.get(league_code, league_code)
    if league_code not in LEAGUE_CODE_MAPPING:
        _log_and_raise("league", f"Unsupported league code '{normalized}'")

    return league_code


def validate_team(
    team: Optional[str], *, required: bool = False, field_name: str = "team"
) -> Optional[str]:
    """Validate a team parameter.

    Parameters
    ----------
    team:
        Raw team name from the request.
    required:
        Whether a value must be provided.
    field_name:
        Custom field name for error reporting.

    Returns
    -------
    Optional[str]
        Normalized team name or ``None`` if not required and missing.

    Raises
    ------
    ValueError
        If the input is missing (and required) or contains unsupported
        characters.
    """

    normalized = _normalize(team)
    if normalized is None:
        if required:
            field_label = field_name.replace('_', ' ')
            _log_and_raise(field_name, f"{field_label} is required")
        return None

    if not _TEAM_PATTERN.fullmatch(normalized):
        field_label = field_name.replace('_', ' ')
        _log_and_raise(
            field_name,
            f"Invalid {field_label}. Only letters, spaces, and .&'()- are allowed.",
        )

    return normalized


def validate_next_days(value: Any) -> int:
    """Validate the ``next_n_days`` parameter.

    Missing values fall back to ``DEFAULT_NEXT_N_DAYS``. Provided values must be
    integers within the inclusive range [1, 90].
    """

    if value is None or (isinstance(value, str) and not value.strip()):
        return DEFAULT_NEXT_N_DAYS

    try:
        parsed = int(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive, covered by ValueError path
        _log_and_raise("next_n_days", "next_n_days must be an integer between 1 and 90")

    if not 1 <= parsed <= 90:
        _log_and_raise("next_n_days", "next_n_days must be between 1 and 90")

    return parsed
