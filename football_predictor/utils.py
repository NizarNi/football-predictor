"""
Utility functions for Football Prediction Platform
Shared helper functions used across multiple modules
"""

from datetime import datetime
from config import (
    SEASON_START_MONTH,
    SEASON_MID_MONTH,
    SEASON_END_MONTH,
    MIN_WORD_LENGTH_FILTER,
    MIN_COMMON_WORDS_MATCH
)


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
