from __future__ import annotations

from ..settings import PROVIDER
from ..adapters.sportmonks import SportmonksAdapter

# Fallbacks
try:
    from ..adapters.fotmob import FotMobAdapter
except Exception:
    FotMobAdapter = None  # type: ignore


def fixtures_adapter():
    """
    Return the adapter to use for fixtures based on settings.PROVIDER.
    - 'sportmonks' -> SportmonksAdapter
    - else -> FotMobAdapter (if available), otherwise Sportmonks as safe default
    """
    if PROVIDER == "sportmonks":
        return SportmonksAdapter()
    if FotMobAdapter is not None:
        return FotMobAdapter()
    return SportmonksAdapter()
