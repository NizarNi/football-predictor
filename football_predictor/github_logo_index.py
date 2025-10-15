import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import requests

from .config import setup_logger

logger = setup_logger(__name__)

GITHUB_OWNER = "luukhopman"
GITHUB_REPO = "football-logos"
GITHUB_TREE_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/trees/master?recursive=1"
)
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/master"

# Cache settings
CACHE_TTL_SECONDS = int(os.environ.get("FP_LOGO_INDEX_TTL", "86400"))  # 24h
REQUEST_TIMEOUT = float(os.environ.get("FP_LOGO_INDEX_TIMEOUT", "5.0"))
GITHUB_TOKEN = os.environ.get("FP_GITHUB_TOKEN")

# In-memory cache
_INDEX: Dict[str, List[str]] = {}
_INDEX_BY_FILE: List[Tuple[str, str, Tuple[str, ...]]] = []
_INDEX_TS: float = 0.0

# Aliases: short names or nicknames -> canonical names (lowercase)
# Based on historical aliases used by the local resolver.
_RAW_ALIASES = {
    # Premier League / England
    "afc bournemouth": "afc bournemouth",
    "bournemouth": "afc bournemouth",
    "arsenal": "arsenal fc",
    "aston villa": "aston villa",
    "brentford": "brentford fc",
    "brighton": "brighton and hove albion",
    "brighton and hove": "brighton and hove albion",
    "burnley": "burnley fc",
    "chelsea": "chelsea fc",
    "palace": "crystal palace",
    "crystal palace": "crystal palace",
    "everton": "everton fc",
    "fulham": "fulham fc",
    "leeds": "leeds united",
    "leeds united": "leeds united",
    "liverpool": "liverpool fc",
    "man utd": "manchester united",
    "manchester utd": "manchester united",
    "man city": "manchester city",
    "manchester city": "manchester city",
    "newcastle": "newcastle united",
    "forest": "nottingham forest",
    "nottm forest": "nottingham forest",
    "sunderland": "sunderland afc",
    "sunderland afc": "sunderland afc",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "west ham": "west ham united",
    "wolves": "wolverhampton wanderers",

    # Ligue 1 / France
    "aj auxerre": "aj auxerre",
    "as monaco": "as monaco",
    "angers": "angers sco",
    "lorient": "fc lorient",
    "metz": "fc metz",
    "nantes": "fc nantes",
    "toulouse": "fc toulouse",
    "losc": "losc lille",
    "lille": "losc lille",
    "le havre": "le havre ac",
    "nice": "ogc nice",
    "olympique lyonnais": "olympique lyon",
    "ol": "olympique lyon",
    "olympique marseille": "olympique marseille",
    "om": "olympique marseille",
    "paris fc": "paris fc",
    "psg": "paris saint germain",
    "paris sg": "paris saint germain",
    "lens": "rc lens",
    "strasbourg": "rc strasbourg alsace",
    "brest": "stade brestois 29",
    "rennes": "stade rennais fc",

    # LaLiga / Spain
    "athletic": "athletic club",
    "athletic bilbao": "athletic club",
    "atleti": "atletico madrid",
    "atletico madrid": "atletico madrid",
    "osasuna": "ca osasuna",
    "celta": "celta de vigo",
    "alaves": "deportivo alaves",
    "barca": "fc barcelona",
    "barcelona": "fc barcelona",
    "getafe": "getafe cf",
    "girona": "girona fc",
    "levante": "levante ud",
    "espanyol": "rcd espanyol",
    "mallorca": "rcd mallorca",
    "rayo": "rayo vallecano",
    "betis": "real betis",
    "real madrid": "real madrid",
    "oviedo": "real oviedo",
    "sociedad": "real sociedad",
    "sevilla": "sevilla fc",
    "valencia": "valencia cf",
    "villarreal": "villarreal cf",

    # Bundesliga / Germany
    "heidenheim": "1 fc heidenheim 1846",
    "koln": "1 fc koln",
    "koeln": "1 fc koln",
    "fc koln": "1 fc koln",
    "1. fc koln": "1 fc koln",
    "union": "1 fc union berlin",
    "mainz": "1 fsv mainz 05",
    "leverkusen": "bayer 04 leverkusen",
    "bayern": "bayern munich",
    "dortmund": "borussia dortmund",
    "monchengladbach": "borussia monchengladbach",
    "moenchengladbach": "borussia monchengladbach",
    "gladbach": "borussia monchengladbach",
    "eintracht": "eintracht frankfurt",
    "augsburg": "fc augsburg",
    "st pauli": "fc st pauli",
    "hamburg": "hamburger sv",
    "leipzig": "rb leipzig",
    "freiburg": "sc freiburg",
    "werder": "sv werder bremen",
    "tsg": "tsg 1899 hoffenheim",
    "vfb": "vfb stuttgart",
    "vfl": "vfl wolfsburg",

    # Serie A / Italy
    "milan": "ac milan",
    "ac milan": "ac milan",
    "fiorentina": "acf fiorentina",
    "roma": "as roma",
    "atalanta": "atalanta bc",
    "bologna": "bologna fc 1909",
    "cagliari": "cagliari calcio",
    "como": "como 1907",
    "genoa": "genoa cfc",
    "verona": "hellas verona",
    "inter": "inter milan",
    "inter milan": "inter milan",
    "juve": "juventus",
    "juventus fc": "juventus",
    "parma": "parma calcio 1913",
    "pisa": "pisa sporting club",
    "lazio": "ss lazio",
    "napoli": "ssc napoli",
    "torino": "torino fc",
    "cremonese": "us cremonese",
    "lecce": "us lecce",
    "sassuolo": "us sassuolo",
    "udinese": "udinese calcio",
}

ALIASES = {k.lower(): v.lower() for k, v in _RAW_ALIASES.items()}

SUPPORTED_EXTENSIONS = (".png", ".svg", ".jpg", ".jpeg", ".webp")


@dataclass(frozen=True)
class _Candidate:
    path: str
    slug: str
    tokens: Tuple[str, ...]


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _tokenize(text: str) -> Tuple[str, ...]:
    cleaned = _strip_accents(text.lower())
    tokens = [tok for tok in re.split(r"[^a-z0-9]+", cleaned) if tok]
    return tuple(tokens)


def _apply_alias(raw: str) -> str:
    base = raw.lower().strip()
    return ALIASES.get(base, base)


def _build_candidate(path: str) -> Optional[_Candidate]:
    basename = os.path.splitext(os.path.basename(path))[0]
    alias_applied = _apply_alias(basename)
    tokens = _tokenize(alias_applied)
    if not tokens:
        return None
    slug = "-".join(tokens)
    return _Candidate(path=path, slug=slug, tokens=tokens)


def _github_headers() -> Dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _refresh_index(force: bool = False) -> None:
    global _INDEX, _INDEX_BY_FILE, _INDEX_TS

    now = time.time()
    if not force and _INDEX and now - _INDEX_TS < CACHE_TTL_SECONDS:
        return

    try:
        response = requests.get(
            GITHUB_TREE_API,
            headers=_github_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        tree = payload.get("tree", [])

        index: Dict[str, List[str]] = {}
        candidates: List[Tuple[str, str, Tuple[str, ...]]] = []

        for entry in tree:
            if entry.get("type") != "blob":
                continue
            path = entry.get("path")
            if not isinstance(path, str):
                continue
            if not path.startswith("logos/"):
                continue
            if not path.lower().endswith(SUPPORTED_EXTENSIONS):
                continue

            candidate = _build_candidate(path)
            if not candidate:
                continue

            index.setdefault(candidate.slug, []).append(candidate.path)
            candidates.append((candidate.path, candidate.slug, candidate.tokens))

        if not candidates:
            raise ValueError("GitHub logo index produced no candidates")

        _INDEX = index
        _INDEX_BY_FILE = candidates
        _INDEX_TS = now

        logger.info("Loaded %d logo entries from GitHub", len(candidates))
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.warning("Failed to refresh GitHub logo index: %s", exc)
        if force:
            # On explicit refresh failures ensure cache is cleared so next call retries.
            _INDEX = {}
            _INDEX_BY_FILE = []
            _INDEX_TS = 0.0


def _choose_exact(slug: str) -> Optional[str]:
    if not slug:
        return None
    paths = _INDEX.get(slug, [])
    if not paths:
        return None
    return _select_preferred(paths)


def _select_preferred(paths: Sequence[str]) -> str:
    def sort_key(p: str) -> Tuple[int, int, str]:
        lowered = p.lower()
        svg_priority = 0 if lowered.endswith(".svg") else 1
        length = len(p)
        return (svg_priority, length, lowered)

    return sorted(paths, key=sort_key)[0]


def _choose_best_match(slug: str, tokens: Tuple[str, ...]) -> Optional[str]:
    best_path: Optional[str] = None
    best_rank: Optional[Tuple[int, float, int, int, int, int, str]] = None

    query_len = len(tokens) or 1
    query_set = set(tokens)

    for path, cand_slug, cand_tokens in _INDEX_BY_FILE:
        common = query_set.intersection(cand_tokens)
        if not common:
            continue
        score = len(common)
        coverage = score / query_len
        slug_match = 1 if cand_slug == slug else 0
        prefix_match = 1 if cand_slug.startswith(slug) or slug.startswith(cand_slug) else 0
        svg_bonus = 1 if path.lower().endswith(".svg") else 0
        rank = (
            score,
            coverage,
            slug_match,
            prefix_match,
            svg_bonus,
            -len(path),
            path.lower(),
        )
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_path = path

    return best_path


def _normalize_input(team: str) -> Tuple[str, Tuple[str, ...]]:
    canonical = _apply_alias(team)
    tokens = _tokenize(canonical)
    slug = "-".join(tokens)
    return slug, tokens


def resolve_remote_logo(team: Optional[str]) -> Optional[str]:
    if not team:
        return None

    slug, tokens = _normalize_input(team)
    if not tokens:
        return None

    _refresh_index()
    if not _INDEX_BY_FILE:
        return None

    exact = _choose_exact(slug)
    if exact:
        return f"{RAW_BASE}/{exact}"

    best = _choose_best_match(slug, tokens)
    if best:
        return f"{RAW_BASE}/{best}"

    return None


def clear_cache() -> None:
    global _INDEX, _INDEX_BY_FILE, _INDEX_TS
    _INDEX = {}
    _INDEX_BY_FILE = []
    _INDEX_TS = 0.0


__all__ = ["resolve_remote_logo", "clear_cache"]
