import os
from dotenv import load_dotenv

# Load .env from repo root (dotenv auto-walks up from CWD)
load_dotenv()


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

# --- Sportmonks settings ---
PROVIDER = os.getenv("PROVIDER", "auto").strip().lower()

def _read_secret_file(path: str | None) -> str | None:
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None

SPORTMONKS_KEY = os.getenv("SPORTMONKS_KEY") or _read_secret_file(os.getenv("SPORTMONKS_KEY_FILE"))
SPORTMONKS_BASE = os.getenv("SPORTMONKS_BASE", "https://api.sportmonks.com/v3/football")
SPORTMONKS_TIMEOUT_MS = int(os.getenv("SPORTMONKS_TIMEOUT_MS", "7000"))
