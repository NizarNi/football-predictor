import os
from typing import Optional

from .config import setup_logger
from .github_logo_index import clear_cache, resolve_remote_logo

logger = setup_logger(__name__)

PKG_DIR = os.path.dirname(__file__)
LOGO_DIR = os.path.join(PKG_DIR, "static", "team_logos")
FALLBACK = os.path.join(LOGO_DIR, "generic_shield.svg")


def resolve_logo(team: Optional[str]) -> str:
    """Resolve a team logo URL or fall back to the local generic shield."""
    url = resolve_remote_logo(team)
    if url:
        return url

    logger.info("Falling back to local shield for team=%s", team)
    return FALLBACK


def reset_logo_cache() -> None:
    """Clear the cached GitHub index (useful for tests)."""
    clear_cache()
