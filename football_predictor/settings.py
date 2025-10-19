import os


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


# --- FotMob feature flag & tunables ---
FOTMOB_ENABLED = _get_bool("FOTMOB_ENABLED", False)
FOTMOB_TIMEOUT_MS = int(os.getenv("FOTMOB_TIMEOUT_MS", "4000"))   # per-call timeout
FOTMOB_PAGE_SIZE = int(os.getenv("FOTMOB_PAGE_SIZE", "25"))       # feed batch size

# (Leave room here for future FotMob settings)
