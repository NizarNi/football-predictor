from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, Optional

from .logging_utils import setup_logger
from .validators import normalize_team_name
from . import name_resolver as _nr
from . import logo_resolver as _lr

log = setup_logger(__name__)
ISO = "%Y-%m-%dT%H:%M:%SZ"


def to_iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime(ISO)


def season_from_iso(iso_str: str) -> str:
    """FotMob season label 'YYYY/YYYY+1' with July rollover."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)
    y = dt.year
    return f"{y}/{y+1}" if dt.month >= 7 else f"{y-1}/{y}"


def normalize_team_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Input varies by source; output unified:
      { id:int, name:str, display_name:str, slug:Optional[str], logo:Optional[str], score:Optional[int] }
    """
    tid = (
        raw.get("id")
        or raw.get("teamId")
        or raw.get("Id")
        or raw.get("HomeTeamId")
        or raw.get("AwayTeamId")
        or 0
    )
    try:
        tid = int(tid) if tid else 0
    except Exception:
        tid = 0

    base = (
        raw.get("name")
        or raw.get("shortName")
        or raw.get("teamName")
        or raw.get("HomeTeam")
        or raw.get("AwayTeam")
        or ""
    )
    name = normalize_team_name(base) or ""
    display = name
    slug: Optional[str] = None
    try:
        if hasattr(_nr, "canonicalize"):
            canon = _nr.canonicalize(name)
            if isinstance(canon, dict):
                display = canon.get("name") or name
                slug = canon.get("slug")
            elif isinstance(canon, str):
                display = canon
    except Exception:
        pass

    logo: Optional[str] = None
    try:
        if hasattr(_lr, "logo_for"):
            logo = _lr.logo_for(display) or _lr.logo_for(name)
    except Exception:
        pass

       # score (preserve zeros; avoid NaN)
    score = None
    for k in ("score", "HomeGoals", "AwayGoals"):
        if k in raw and raw[k] is not None:
            score = raw[k]
            break
    # coerce to int if possible; treat NaN as None
    try:
        # float('nan') != float('nan') -> True; catches NaN
        if score is not None and not (isinstance(score, float) and score != score):
            score = int(score)
        else:
            score = None
    except Exception:
        score = None

    return {
        "id": tid,
        "name": name,
        "display_name": display,
        "slug": slug,
        "logo": logo,
        "score": score,
    }
