from typing import Optional, Tuple, List
from .constants import LEAGUE_CODE_MAPPING
from .config import setup_logger

logger = setup_logger(__name__)

LEAGUE_ALIAS_MAPPING = {
    "EPL": "PL",
    "PREMIER_LEAGUE": "PL",
    "ENGLISH_PREMIER_LEAGUE": "PL",
    "LA_LIGA": "PD",
    "LALIGA": "PD",
    "SPANISH_LA_LIGA": "PD",
    "BUNDESLIGA": "BL1",
    "SERIE_A": "SA",
    "SERIEA": "SA",
    "LIGUE_1": "FL1",
    "LIGUE1": "FL1",
    "CHAMPIONS_LEAGUE": "CL",
    "EUROPA_LEAGUE": "EL",
}


class ValidationWarning(str):
    """Lightweight tag for soft validation warnings."""
    pass


def validate_league(code: Optional[str]) -> Tuple[Optional[str], List[ValidationWarning]]:
    """Return (normalized_league_code_or_None, warnings). Soft-fails on unknown/missing."""
    if not code:
        return None, [ValidationWarning("league_missing")]
    c = str(code).upper().strip()
    alias_key = c.replace(" ", "_")
    if c in LEAGUE_CODE_MAPPING:
        return c, []
    alias_match = LEAGUE_ALIAS_MAPPING.get(alias_key)
    if alias_match:
        return alias_match, []
    logger.warning("league_unknown: %s", c)
    return None, [ValidationWarning(f"league_unknown:{c}")]


def validate_next_n_days(raw: Optional[int], default: int = 30, min_v: int = 1, max_v: int = 60):
    """Coerce to int and clamp to [min_v,max_v]. Return (value, warnings)."""
    if raw is None:
        return default, []
    try:
        v = int(raw)
    except Exception:
        logger.warning("next_n_days_invalid: %s", raw)
        return default, [ValidationWarning("next_n_days_invalid")]
    if v < min_v:
        logger.warning("next_n_days_floor: %s -> %s", v, min_v)
        return min_v, [ValidationWarning("next_n_days_floor")]
    if v > max_v:
        logger.warning("next_n_days_cap: %s -> %s", v, max_v)
        return max_v, [ValidationWarning("next_n_days_cap")]
    return v, []


def normalize_team_name(name: Optional[str]) -> Optional[str]:
    """Trim/collapse spaces and Title-Case; return None if empty."""
    if not name:
        return None
    n = " ".join(str(name).strip().split())
    return n.title() if n else None


def validate_team_optional(name: Optional[str]):
    """Soft validation for optional team fields. Always returns (normalized_or_None, [])."""
    n = normalize_team_name(name)
    return n, []


# FotMob competition validation helpers
try:
    from .constants import FOTMOB_COMP_CODES, is_supported_fotmob_comp
except Exception:
    # Keep imports safe if constants change
    FOTMOB_COMP_CODES = tuple()

    def is_supported_fotmob_comp(_: str) -> bool:  # type: ignore
        return False


def validate_fotmob_comp(code: str) -> str:
    """Normalize and validate FotMob competition code."""

    c = (code or "").strip().upper()
    if is_supported_fotmob_comp(c):
        return c
    allowed = ", ".join(FOTMOB_COMP_CODES) if FOTMOB_COMP_CODES else "<none>"
    raise ValueError(f"Unsupported competition code: {c}. Allowed: {allowed}")
