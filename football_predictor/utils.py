"""
Utility functions for Football Prediction Platform
Shared helper functions used across multiple modules
"""

import logging
from datetime import datetime
from typing import Any, Callable, Iterable, Optional

import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import quote

from .config import (
    SEASON_START_MONTH,
    SEASON_MID_MONTH,
    SEASON_END_MONTH,
    MIN_WORD_LENGTH_FILTER,
    MIN_COMMON_WORDS_MATCH
)


logger = logging.getLogger(__name__)

LOGO_BASE_URL = "https://raw.githubusercontent.com/luukhopman/football-logos/master/logos"

LEAGUE_LOGO_DIRECTORIES = {
    "PL": "Premier League",
    "PD": "La Liga",
    "BL1": "Bundesliga",
    "SA": "Serie A",
    "FL1": "Ligue 1",
    "CL": "UEFA Champions League",
    "EL": "UEFA Europa League",
}


def _logo_override_key(name: str) -> str:
    return name.strip().lower()


TEAM_LOGO_OVERRIDES = {
    _logo_override_key("Sunderland"): "Sunderland AFC",
    _logo_override_key("Leeds"): "Leeds United",
    _logo_override_key("Spurs"): "Tottenham Hotspur",
    _logo_override_key("Man United"): "Manchester United",
    _logo_override_key("Man Utd"): "Manchester United",
    _logo_override_key("Man City"): "Manchester City",
    _logo_override_key("Newcastle"): "Newcastle United",
    _logo_override_key("Wolves"): "Wolverhampton Wanderers",
    _logo_override_key("Bayern Munich"): "Bayern Munich",
    _logo_override_key("Paris SG"): "Paris Saint-Germain",
    _logo_override_key("PSG"): "Paris Saint-Germain",
    _logo_override_key("default"): "/static/images/default_badge.png",
}


_LOGO_URL_CACHE: dict[str, bool] = {}


def get_current_season():
    """
    Calculate current football season END YEAR for Understat.
    
    Understat uses END YEAR for season naming (2025-2026 season = 2026).
    Football seasons run August to May:
    - August-December (months 8-12): Return current year + 1 (e.g., Oct 2025 → 2026 for 2025-2026 season)
    - January-July (months 1-7): Return current year (e.g., Jan 2026 → 2026 for 2025-2026 season)
    
    Returns:
        int: Current season END YEAR for Understat (e.g., 2026 for 2025-2026 season)
    """
    today = datetime.now()
    if today.month >= SEASON_START_MONTH:
        return today.year + 1  # Aug-Dec: return next year as END YEAR
    else:
        return today.year  # Jan-Jul: return current year as END YEAR


def get_xg_season():
    """
    Determine current season START YEAR for FBref/soccerdata.
    
    FBref uses START YEAR for season naming (2025-2026 season = 2025).
    Always returns the current season start year.
    
    Logic:
    - August-December: Return current year as START YEAR (e.g., Oct 2025 → 2025 for 2025-2026 season)
    - January-July: Return previous year as START YEAR (e.g., Jan 2026 → 2025 for 2025-2026 season)
    
    Returns:
        int: Current season START YEAR for FBref (e.g., 2025 for 2025-2026 season)
    """
    now = datetime.now()
    return now.year if now.month >= SEASON_START_MONTH else now.year - 1


def normalize_team_name(name):
    """
    Normalize team name for better matching across data sources.
    
    Removes common prefixes/suffixes and standardizes format for fuzzy matching.
    
    Args:
        name (str): Team name to normalize
        
    Returns:
        str: Normalized team name
    """
    if not name:
        return ""
    
    # Convert to lowercase
    normalized = name.lower()
    
    # Remove common prefixes and suffixes
    prefixes = ['fc ', 'afc ', 'cf ', 'ac ', 'sc ', 'ssc ', 'as ', 'rc ', 'rcd ', 'fk ', 'bfc ', 'vfl ', 'sv ']
    suffixes = [' fc', ' afc', ' cf', ' ac', ' sc', ' united', ' city', ' town']
    
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            break
    
    # Replace variations
    normalized = normalized.replace(' and ', ' & ')
    normalized = normalized.replace('&', 'and')
    
    # Remove extra spaces
    normalized = ' '.join(normalized.split())
    
    return normalized


def fuzzy_team_match(team1, team2, min_word_length=MIN_WORD_LENGTH_FILTER, min_common_words=MIN_COMMON_WORDS_MATCH):
    """
    Check if two team names match with fuzzy logic.
    
    Uses multiple strategies: exact match, contains match, normalized match, and word-based matching.
    
    Args:
        team1 (str): First team name
        team2 (str): Second team name
        min_word_length (int): Minimum word length for matching (default: MIN_WORD_LENGTH_FILTER from config)
        min_common_words (int): Minimum common words required (default: MIN_COMMON_WORDS_MATCH from config)
        
    Returns:
        bool: True if teams match, False otherwise
    """
    if not team1 or not team2:
        return False
    
    t1_lower = team1.lower()
    t2_lower = team2.lower()
    
    # Exact match
    if t1_lower == t2_lower:
        return True
    
    # Contains match
    if t1_lower in t2_lower or t2_lower in t1_lower:
        return True
    
    # Normalized match
    t1_norm = normalize_team_name(team1)
    t2_norm = normalize_team_name(team2)
    
    if t1_norm == t2_norm:
        return True
    
    # Normalized contains match
    if t1_norm in t2_norm or t2_norm in t1_norm:
        return True
    
    # Word-based match (at least min_common_words significant words match)
    words1 = set(t1_norm.split())
    words2 = set(t2_norm.split())
    
    # Filter out very short words (articles, etc.)
    words1 = {w for w in words1 if len(w) > min_word_length}
    words2 = {w for w in words2 if len(w) > min_word_length}
    
    common_words = words1 & words2
    if len(common_words) >= min(min_common_words, len(words1), len(words2)):
        return True
    
    return False


def get_team_abbreviation(team_name):
    """
    Get 3-letter abbreviation for a team name.
    
    Args:
        team_name (str): Full team name
        
    Returns:
        str: 3-letter abbreviation (uppercase)
    """
    # Common team abbreviations mapping
    abbreviations = {
        # Premier League
        'Manchester City': 'MCI',
        'Man City': 'MCI',
        'Manchester United': 'MUN',
        'Man United': 'MUN',
        'Man Utd': 'MUN',
        'Liverpool': 'LIV',
        'Chelsea': 'CHE',
        'Arsenal': 'ARS',
        'Tottenham': 'TOT',
        'Tottenham Hotspur': 'TOT',
        'Newcastle': 'NEW',
        'Newcastle United': 'NEW',
        'Aston Villa': 'AVL',
        'Brighton': 'BHA',
        'West Ham': 'WHU',
        'West Ham United': 'WHU',
        'Everton': 'EVE',
        'Leicester': 'LEI',
        'Leicester City': 'LEI',
        'Wolves': 'WOL',
        'Wolverhampton': 'WOL',
        'Crystal Palace': 'CRY',
        'Fulham': 'FUL',
        'Brentford': 'BRE',
        'Nottingham Forest': 'NFO',
        'Bournemouth': 'BOU',
        'Southampton': 'SOU',
        'Ipswich': 'IPS',
        'Ipswich Town': 'IPS',
        
        # La Liga
        'Real Madrid': 'RMA',
        'Barcelona': 'BAR',
        'Atletico Madrid': 'ATM',
        'Atlético Madrid': 'ATM',
        'Sevilla': 'SEV',
        'Valencia': 'VAL',
        'Villarreal': 'VIL',
        'Real Sociedad': 'RSO',
        'Real Betis': 'BET',
        'Athletic Bilbao': 'ATH',
        'Athletic Club': 'ATH',
        'Celta Vigo': 'CEL',
        'Getafe': 'GET',
        'Osasuna': 'OSA',
        'Girona': 'GIR',
        'Mallorca': 'MAL',
        'Las Palmas': 'LPA',
        'Rayo Vallecano': 'RAY',
        'Alaves': 'ALA',
        'Alavés': 'ALA',
        'Espanyol': 'ESP',
        'Valladolid': 'VLD',
        
        # Bundesliga
        'Bayern Munich': 'BAY',
        'Bayern München': 'BAY',
        'Borussia Dortmund': 'BVB',
        'RB Leipzig': 'RBL',
        'Bayer Leverkusen': 'B04',
        'Union Berlin': 'FCU',
        'Freiburg': 'SCF',
        'Eintracht Frankfurt': 'SGE',
        'Wolfsburg': 'WOB',
        'Mainz': 'M05',
        'Borussia Monchengladbach': 'BMG',
        "Borussia M'gladbach": 'BMG',
        'Hoffenheim': 'TSG',
        'Werder Bremen': 'SVW',
        'Stuttgart': 'VFB',
        'Augsburg': 'FCA',
        'Heidenheim': 'HDH',
        'St Pauli': 'STP',
        'Holstein Kiel': 'KIE',
        
        # Serie A
        'Inter': 'INT',
        'Inter Milan': 'INT',
        'Internazionale': 'INT',
        'AC Milan': 'MIL',
        'Milan': 'MIL',
        'Juventus': 'JUV',
        'Napoli': 'NAP',
        'Roma': 'ROM',
        'Lazio': 'LAZ',
        'Atalanta': 'ATA',
        'Fiorentina': 'FIO',
        'Bologna': 'BOL',
        'Torino': 'TOR',
        'Udinese': 'UDI',
        'Monza': 'MON',
        'Genoa': 'GEN',
        'Lecce': 'LEC',
        'Parma': 'PAR',
        'Cagliari': 'CAG',
        'Empoli': 'EMP',
        'Hellas Verona': 'VER',
        'Venezia': 'VEN',
        'Como': 'COM',
        
        # Ligue 1
        'Paris Saint Germain': 'PSG',
        'Paris SG': 'PSG',
        'Marseille': 'OMA',
        'Monaco': 'ASM',
        'Lyon': 'OLY',
        'Lille': 'LIL',
        'Nice': 'OGC',
        'Lens': 'RCL',
        'Rennes': 'STA',
        'Brest': 'SB29',
        'Strasbourg': 'RCS',
        'Toulouse': 'TFC',
        'Nantes': 'FCN',
        'Montpellier': 'MHC',
        'Reims': 'SDE',
        'Saint-Etienne': 'ASS',
        'Le Havre': 'HAC',
        'Angers': 'SCO',
        'Auxerre': 'AJA'
    }
    
    # Check if we have a direct mapping
    if team_name in abbreviations:
        return abbreviations[team_name]
    
    # Fallback: take first 3 letters of first word (uppercase)
    words = team_name.split()
    if words:
        first_word = words[0].upper()
        return first_word[:3]

    return team_name[:3].upper()


def _resolve_logo_directory(league: Optional[str]) -> Optional[str]:
    if not league:
        return None

    code = league.strip()
    if not code:
        return None

    directory = LEAGUE_LOGO_DIRECTORIES.get(code.upper())
    if directory:
        return directory

    return code


def _logo_url_exists(url: str) -> bool:
    if url in _LOGO_URL_CACHE:
        return _LOGO_URL_CACHE[url]

    try:
        response = requests.head(url, allow_redirects=True, timeout=0.5)
        exists = response.status_code != 404
    except requests.RequestException as exc:
        logger.debug("Logo availability check failed for %s: %s", url, exc)
        exists = True

    _LOGO_URL_CACHE[url] = exists
    return exists


def get_team_logo(team_name: Optional[str], league: Optional[str]) -> str:
    """Return a normalized logo URL for the given team and league."""

    default_logo = TEAM_LOGO_OVERRIDES[_logo_override_key("default")]

    if not team_name:
        logger.warning("Missing team name for logo lookup (league=%s)", league)
        return default_logo

    league_directory = _resolve_logo_directory(league)
    if not league_directory:
        logger.warning("Missing league for team '%s' when resolving logo", team_name)
        return default_logo

    lookup_keys = {
        _logo_override_key(team_name),
        _logo_override_key(normalize_team_name(team_name)),
    }

    filename: Optional[str] = None
    for key in lookup_keys:
        if key in TEAM_LOGO_OVERRIDES and key != _logo_override_key("default"):
            filename = TEAM_LOGO_OVERRIDES[key]
            break

    if filename is None:
        filename = team_name.strip()

    if not filename:
        logger.warning(
            "Resolved empty filename while looking up logo for team '%s' (league=%s)",
            team_name,
            league,
        )
        return default_logo

    encoded_league = quote(league_directory, safe="")
    encoded_filename = quote(filename, safe="")
    logo_url = f"{LOGO_BASE_URL}/{encoded_league}/{encoded_filename}.png"

    if not _logo_url_exists(logo_url):
        logger.warning(
            "Logo missing at %s for team '%s' in league '%s'", logo_url, team_name, league
        )
        return default_logo

    return logo_url


_DEFAULT_ALLOWED_METHODS: frozenset[str] = frozenset(
    ["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE", "PATCH"]
)
_DEFAULT_STATUS_FORCELIST: tuple[int, ...] = (429, 500, 502, 503, 504)


def create_retry_session(
    max_retries: int,
    backoff_factor: float,
    status_forcelist: Iterable[int] | None = None,
) -> requests.Session:
    """Create a configured :class:`requests.Session` with retry adapters."""

    retry_adapter = HTTPAdapter(
        max_retries=Retry(
            total=0,
            connect=0,
            read=0,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist or _DEFAULT_STATUS_FORCELIST,
            allowed_methods=_DEFAULT_ALLOWED_METHODS,
            raise_on_status=False,
        )
    )

    session = requests.Session()
    session.mount("https://", retry_adapter)
    session.mount("http://", retry_adapter)
    return session


def _sanitize_value(value: Any, sanitizer: Optional[Callable[[str], str]] = None) -> str:
    text = "" if value is None else str(value)
    if sanitizer is None:
        return text
    try:
        return sanitizer(text)
    except Exception:
        return text


def request_with_retries(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: float,
    max_retries: int,
    backoff_factor: float,
    status_forcelist: Iterable[int] | None,
    logger,
    context: str,
    sanitize: Optional[Callable[[str], str]] = None,
    **kwargs: Any,
) -> requests.Response:
    """Perform an HTTP request with retry and logging support."""

    retry_state = Retry(
        total=max_retries,
        connect=max_retries,
        read=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=tuple(status_forcelist or _DEFAULT_STATUS_FORCELIST),
        allowed_methods=_DEFAULT_ALLOWED_METHODS,
        raise_on_status=False,
    )

    attempts = 0
    attempted_retries = 0
    last_exception: Optional[requests.exceptions.RequestException] = None

    while attempts < max_retries:
        attempts += 1
        response: Optional[requests.Response] = None

        try:
            response = session.request(method, url, timeout=timeout, **kwargs)
            if response.status_code in retry_state.status_forcelist:
                raise requests.exceptions.HTTPError(
                    f"{response.status_code} Server Error: {response.reason}",
                    response=response,
                )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as exc:
            last_exception = exc
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            should_retry = attempts < max_retries and (
                isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError))
                or status_code in retry_state.status_forcelist
            )

            if not should_retry:
                break

            attempted_retries += 1
            retry_state = retry_state.increment(
                method=method,
                url=url,
                response=getattr(exc, "response", None) or response,
                error=exc,
            )
            backoff = retry_state.get_backoff_time()

            logger.warning(
                "Retrying %s (%d/%d): %s - %s",
                context,
                attempts,
                max_retries,
                _sanitize_value(url, sanitize),
                _sanitize_value(exc, sanitize),
            )

            if backoff > 0:
                time.sleep(backoff)

    if last_exception is not None:
        if attempted_retries > 0 or attempts >= max_retries:
            logger.error(
                "Failed %s after %d attempts: %s",
                context,
                max_retries,
                _sanitize_value(last_exception, sanitize),
            )
        raise last_exception

    raise RuntimeError("request_with_retries exited without attempting a request")
