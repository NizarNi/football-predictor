from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .validators import normalize_team_name
from . import name_resolver as _nr
from . import logo_resolver as _lr
from .config import setup_logger

log = setup_logger(__name__)

ISO = "%Y-%m-%dT%H:%M:%SZ"


def to_iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime(ISO)


def season_from_iso(iso_str: str) -> str:
    """FotMob season label: 'YYYY/YYYY+1' with July rollover."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)
    year = dt.year
    if dt.month >= 7:
        return f"{year}/{year + 1}"
    return f"{year - 1}/{year}"


def _extract_team_id(raw: Dict[str, Any]) -> int:
    tid: Optional[Any] = (
        raw.get("id")
        or raw.get("teamId")
        or raw.get("Id")
        or raw.get("HomeTeamId")
        or raw.get("AwayTeamId")
        or 0
    )
    try:
        return int(tid) if tid else 0
    except Exception:
        return 0


def _extract_team_name(raw: Dict[str, Any]) -> str:
    base = (
        raw.get("name")
        or raw.get("shortName")
        or raw.get("teamName")
        or raw.get("HomeTeam")
        or raw.get("AwayTeam")
        or ""
    )
    return normalize_team_name(base) or ""


def _resolve_canonical(name: str) -> tuple[str, Optional[str]]:
    display = name
    slug: Optional[str] = None
    try:
        if hasattr(_nr, "canonicalize"):
            canon = _nr.canonicalize(name)
            if isinstance(canon, dict):
                display = canon.get("name") or display
                slug = canon.get("slug")
            elif isinstance(canon, str):
                display = canon
    except Exception as exc:  # pragma: no cover - defensive logging
        log.debug("fotmob_shared.canonicalize_failed name=%s err=%s", name, exc)
    return display, slug


def _resolve_logo(display: str, fallback: str) -> Optional[str]:
    logo: Optional[str] = None
    try:
        if hasattr(_lr, "logo_for"):
            logo = _lr.logo_for(display) or _lr.logo_for(fallback)
    except Exception as exc:  # pragma: no cover - defensive logging
        log.debug("fotmob_shared.logo_lookup_failed name=%s err=%s", display, exc)
    return logo


def _extract_score(raw: Dict[str, Any]) -> Optional[int]:
    score = raw.get("score") or raw.get("HomeGoals") or raw.get("AwayGoals")
    try:
        if score is None or score != score:  # NaN guard
            return None
        return int(score)
    except Exception:
        return None


def normalize_team_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Input raw team dict (varies by source). Output unified:
      { id:int, name:str, display_name:str, score:Optional[int], slug:Optional[str], logo:Optional[str] }
    """

    team_id = _extract_team_id(raw)
    name = _extract_team_name(raw)
    display_name, slug = _resolve_canonical(name)
    logo = _resolve_logo(display_name, name)
    score = _extract_score(raw)

    return {
        "id": team_id,
        "name": name,
        "display_name": display_name,
        "slug": slug,
        "logo": logo,
        "score": score,
    }
