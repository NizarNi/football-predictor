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
    Calculate current football season based on calendar month.
    
    Football seasons run August to May:
    - August-December (months 8-12): Use current year as season (e.g., Oct 2025 → Season 2025)
    - January-July (months 1-7): Use previous year as season (e.g., Jan 2026 → Season 2025)
    
    Returns:
        int: Current season year (e.g., 2025)
    """
    today = datetime.now()
    return today.year if today.month >= SEASON_START_MONTH else today.year - 1


def get_xg_season():
    """
    Determine current season for xG data with conservative approach.
    
    Football season typically starts in August, but early season has limited data.
    Use previous season data until December to have substantial statistics.
    
    Logic:
    - December onwards: Use current season (enough data accumulated)
    - August-November: Use previous season (more complete data)
    - January-July: Use previous season (standard)
    
    Returns:
        int: Season year for xG data (e.g., 2024 for conservative stats)
    """
    now = datetime.now()
    
    # December onwards, use current season
    if now.month >= SEASON_MID_MONTH:
        return now.year if now.month >= SEASON_START_MONTH else now.year - 1
    # August-November, use previous season (more complete data)
    elif now.month >= SEASON_START_MONTH:
        return now.year - 1
    # January-July, use previous season
    else:
        return now.year - 1


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
