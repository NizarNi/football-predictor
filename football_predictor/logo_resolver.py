import os
import re
import unicodedata
from typing import Optional, List, Tuple

from .config import setup_logger

logger = setup_logger(__name__)

PKG_DIR = os.path.dirname(__file__)
LOGO_DIR = os.path.join(PKG_DIR, "static", "team_logos")
FALLBACK = os.path.join(LOGO_DIR, "generic_shield.svg")

# Aliases: common short names/nicknames/abbreviations → canonical display names (as used in filenames)
ALIASES = {
    # Premier League / England
    "afc bournemouth": "AFC Bournemouth",
    "bournemouth": "AFC Bournemouth",
    "arsenal": "Arsenal FC",
    "aston villa": "Aston Villa",
    "brentford": "Brentford FC",
    "brighton": "Brighton & Hove Albion",
    "brighton and hove": "Brighton & Hove Albion",
    "burnley": "Burnley FC",
    "chelsea": "Chelsea FC",
    "palace": "Crystal Palace",
    "everton": "Everton FC",
    "fulham": "Fulham FC",
    "leeds": "Leeds United",
    "liverpool": "Liverpool FC",
    "man utd": "Manchester United",
    "manchester utd": "Manchester United",
    "man city": "Manchester City",
    "manchester city": "Manchester City",
    "newcastle": "Newcastle United",
    "forest": "Nottingham Forest",
    "sunderland": "Sunderland AFC",
    "spurs": "Tottenham Hotspur",
    "west ham": "West Ham United",
    "wolves": "Wolverhampton Wanderers",

    # Ligue 1 / France
    "aj auxerre": "AJ Auxerre",
    "as monaco": "AS Monaco",
    "angers": "Angers SCO",
    "lorient": "FC Lorient",
    "metz": "FC Metz",
    "nantes": "FC Nantes",
    "toulouse": "FC Toulouse",
    "losc": "LOSC Lille",
    "lille": "LOSC Lille",
    "le havre": "Le Havre AC",
    "nice": "OGC Nice",
    "olympique lyonnais": "Olympique Lyon",
    "ol": "Olympique Lyon",
    "olympique marseille": "Olympique Marseille",
    "om": "Olympique Marseille",
    "paris fc": "Paris FC",
    "psg": "Paris Saint-Germain",
    "paris sg": "Paris Saint-Germain",
    "lens": "RC Lens",
    "strasbourg": "RC Strasbourg Alsace",
    "brest": "Stade Brestois 29",
    "rennes": "Stade Rennais FC",

    # LaLiga / Spain
    "athletic": "Athletic Bilbao",
    "atleti": "Atlético de Madrid",
    "atletico madrid": "Atlético de Madrid",
    "osasuna": "CA Osasuna",
    "celta": "Celta de Vigo",
    "alaves": "Deportivo Alavés",
    "barca": "FC Barcelona",
    "getafe": "Getafe CF",
    "girona": "Girona FC",
    "levante": "Levante UD",
    "espanyol": "RCD Espanyol Barcelona",
    "mallorca": "RCD Mallorca",
    "rayo": "Rayo Vallecano",
    "betis": "Real Betis Balompié",
    "real madrid": "Real Madrid",
    "oviedo": "Real Oviedo",
    "sociedad": "Real Sociedad",
    "sevilla": "Sevilla FC",
    "valencia": "Valencia CF",
    "villarreal": "Villarreal CF",

    # Bundesliga / Germany
    "heidenheim": "1.FC Heidenheim 1846",
    "koln": "1.FC Köln",
    "koeln": "1.FC Köln",
    "fc koln": "1.FC Köln",
    "union": "1.FC Union Berlin",
    "mainz": "1.FSV Mainz 05",
    "leverkusen": "Bayer 04 Leverkusen",
    "bayern": "Bayern Munich",
    "dortmund": "Borussia Dortmund",
    "monchengladbach": "Borussia Mönchengladbach",
    "moenchengladbach": "Borussia Mönchengladbach",
    "gladbach": "Borussia Mönchengladbach",
    "eintracht": "Eintracht Frankfurt",
    "augsburg": "FC Augsburg",
    "st pauli": "FC St. Pauli",
    "hamburg": "Hamburger SV",
    "leipzig": "RB Leipzig",
    "freiburg": "SC Freiburg",
    "werder": "SV Werder Bremen",
    "tsg": "TSG 1899 Hoffenheim",
    "vfb": "VfB Stuttgart",
    "vfl": "VfL Wolfsburg",

    # Serie A / Italy
    "milan": "AC Milan",
    "fiorentina": "ACF Fiorentina",
    "roma": "AS Roma",
    "atalanta": "Atalanta BC",
    "bologna": "Bologna FC 1909",
    "cagliari": "Cagliari Calcio",
    "como": "Como 1907",
    "genoa": "Genoa CFC",
    "verona": "Hellas Verona",
    "inter": "Inter Milan",
    "juve": "Juventus FC",
    "parma": "Parma Calcio 1913",
    "pisa": "Pisa Sporting Club",
    "lazio": "SS Lazio",
    "napoli": "SSC Napoli",
    "torino": "Torino FC",
    "cremonese": "US Cremonese",
    "lecce": "US Lecce",
    "sassuolo": "US Sassuolo",
    "udinese": "Udinese Calcio",
}

def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _normalize(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace, remove punctuation (keep alnum + spaces)."""
    s = _strip_accents(s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _basename_no_ext(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _iter_logo_files(root: str) -> List[str]:
    files = []
    if not os.path.isdir(root):
        return files
    for base, _dirs, names in os.walk(root):
        for n in names:
            if n.lower().endswith((".png", ".svg", ".jpg", ".jpeg", ".webp")):
                files.append(os.path.join(base, n))
    return files


def _build_index() -> List[Tuple[str, str, List[str]]]:
    """List of (abs_path, normalized_basename, tokens)"""
    index = []
    for abs_path in _iter_logo_files(LOGO_DIR):
        base = _basename_no_ext(abs_path)
        norm = _normalize(base)
        tokens = norm.split(" ") if norm else []
        index.append((abs_path, norm, tokens))
    return index


_LOGO_INDEX: Optional[List[Tuple[str, str, List[str]]]] = None


def _get_index():
    global _LOGO_INDEX
    if _LOGO_INDEX is None:
        _LOGO_INDEX = _build_index()
    return _LOGO_INDEX


def _alias_or_raw(name: str) -> str:
    key = _normalize(name)
    return ALIASES.get(key, name)


def _score_token_match(query_tokens: List[str], candidate_tokens: List[str]) -> int:
    return len(set(query_tokens) & set(candidate_tokens))


def _try_exact_basename(norm_query: str) -> Optional[str]:
    if not norm_query:
        return None
    for abs_path, cand_norm, _tok in _get_index():
        if cand_norm == norm_query:
            return abs_path
    return None


def resolve_logo(team: Optional[str]) -> str:
    """Resolve a team logo absolute path under the package static directory."""
    if not os.path.isdir(LOGO_DIR) or not team:
        return FALLBACK

    norm_query = _normalize(team.strip())
    path = _try_exact_basename(norm_query)
    if path:
        return path

    alias = _alias_or_raw(team)
    if alias != team:
        alias_path = _try_exact_basename(_normalize(alias))
        if alias_path:
            return alias_path

    q_tokens = norm_query.split(" ") if norm_query else []
    best_score = 0
    best_path = None
    for abs_path, _cand_norm, cand_tokens in _get_index():
        score = _score_token_match(q_tokens, cand_tokens)
        if score > best_score:
            best_score = score
            best_path = abs_path

    if best_path and best_score > 0:
        return best_path

    logger.info("Logo fallback for team=%s", team)
    return FALLBACK


def reset_logo_cache() -> None:
    """Clear the cached logo index (useful for tests)."""
    global _LOGO_INDEX
    _LOGO_INDEX = None
