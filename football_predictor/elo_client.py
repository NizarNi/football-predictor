"""
Elo Rating Client for FPL-Elo-Insights Repository
Fetches team Elo ratings from GitHub, updated twice daily (5am/5pm UTC)
"""

import requests
import csv
from datetime import datetime, timedelta
from io import StringIO
from typing import Optional, Dict, Any
import os
from config import (
    ELO_CACHE_DURATION_HOURS, 
    API_TIMEOUT_ELO, 
    HYBRID_ELO_WEIGHT, 
    HYBRID_MARKET_WEIGHT,
    TEAM_NAME_MAP_ELO as TEAM_NAME_MAP
)

# ClubElo.com API - Original source for Elo ratings
# Format: http://api.clubelo.com/{date} where date is YYYY-MM-DD
# Returns global rankings with Elo ratings for all clubs

# Cache configuration
_elo_cache: Dict[str, Optional[Any]] = {
    "data": None,
    "timestamp": None
}


def fetch_team_elo_ratings():
    """
    Fetch the latest team Elo ratings from ClubElo.com API.
    Returns a dictionary mapping team names to their current Elo ratings.
    
    Returns:
        dict: {team_name: elo_rating} or None if fetch fails
    """
    # Check cache first
    if _elo_cache["data"] and _elo_cache["timestamp"]:
        cache_age = datetime.now() - _elo_cache["timestamp"]
        if cache_age < timedelta(hours=ELO_CACHE_DURATION_HOURS):
            print(f"✅ Using cached Elo ratings (age: {cache_age.seconds // 3600}h {(cache_age.seconds % 3600) // 60}m)")
            return _elo_cache["data"]
    
    try:
        print("🔍 Fetching latest Elo ratings from ClubElo.com...")
        
        # ClubElo API requires date parameter (YYYY-MM-DD)
        today = datetime.now().strftime("%Y-%m-%d")
        api_url = f"http://api.clubelo.com/{today}"
        
        # Fetch global Elo ratings from ClubElo API
        response = requests.get(api_url, timeout=API_TIMEOUT_ELO)
        response.raise_for_status()
        
        # Parse CSV data
        team_elo_ratings = {}
        reader = csv.DictReader(StringIO(response.text))
        
        # ClubElo CSV format: Club,Country,Level,Elo,From,To
        # We want the latest Elo for each team
        for row in reader:
            team_name = row.get('Club')
            elo_rating = row.get('Elo')
            
            if team_name and elo_rating:
                try:
                    # Always update - the API returns latest first
                    team_elo_ratings[team_name] = float(elo_rating)
                except ValueError:
                    pass
        
        if team_elo_ratings:
            # Update cache
            _elo_cache["data"] = team_elo_ratings
            _elo_cache["timestamp"] = datetime.now()
            print(f"✅ Successfully fetched Elo ratings for {len(team_elo_ratings)} teams")
            return team_elo_ratings
        else:
            print("⚠️ No Elo ratings found in ClubElo data")
            return None
    
    except Exception as e:
        print(f"❌ Error fetching Elo ratings: {e}")
        # Return cached data if available, even if expired
        if _elo_cache["data"]:
            print("⚠️ Using expired cache due to fetch error")
            return _elo_cache["data"]
        return None


def get_team_elo(team_name):
    """
    Get the current Elo rating for a specific team.
    Uses alias mapping to handle variations in team names.
    
    Args:
        team_name (str): Name of the team
        
    Returns:
        float: Elo rating or None if not found
    """
    elo_ratings = fetch_team_elo_ratings()
    if not elo_ratings:
        return None
    
    # Step 1: Check alias map first
    mapped_name = TEAM_NAME_MAP.get(team_name)
    if mapped_name and mapped_name in elo_ratings:
        print(f"✅ Mapped '{team_name}' → '{mapped_name}' (Elo: {elo_ratings[mapped_name]:.1f})")
        return elo_ratings[mapped_name]
    
    # Step 2: Try exact match
    if team_name in elo_ratings:
        print(f"✅ Exact match '{team_name}' (Elo: {elo_ratings[team_name]:.1f})")
        return elo_ratings[team_name]
    
    # Step 3: Try case-insensitive match
    team_name_lower = team_name.lower()
    for elo_team_name, elo_rating in elo_ratings.items():
        if elo_team_name.lower() == team_name_lower:
            print(f"✅ Case-insensitive match '{team_name}' → '{elo_team_name}' (Elo: {elo_rating:.1f})")
            return elo_rating
    
    # Step 4: Try partial matching (substring)
    for elo_team_name, elo_rating in elo_ratings.items():
        if team_name_lower in elo_team_name.lower() or elo_team_name.lower() in team_name_lower:
            print(f"✅ Partial match '{team_name}' → '{elo_team_name}' (Elo: {elo_rating:.1f})")
            return elo_rating
    
    # Team not found - this is expected for smaller teams/leagues not tracked by ClubElo
    print(f"ℹ️  Elo rating unavailable for '{team_name}' (team not in ClubElo database)")
    return None


def calculate_elo_probabilities(home_elo, away_elo):
    """
    Calculate win/draw/lose probabilities based on Elo ratings.
    Uses the standard Elo formula: P(A wins) = 1 / (1 + 10^((Elo_B - Elo_A)/400))
    
    Args:
        home_elo (float): Home team's Elo rating
        away_elo (float): Away team's Elo rating
        
    Returns:
        dict: {"home_win": float, "draw": float, "away_win": float}
    """
    if home_elo is None or away_elo is None:
        return None
    
    # Standard Elo win probability formula
    elo_diff = away_elo - home_elo
    home_win_prob = 1 / (1 + 10 ** (elo_diff / 400))
    away_win_prob = 1 - home_win_prob
    
    # Estimate draw probability (typically 25-30% in football)
    # Adjust based on Elo difference - closer teams = higher draw probability
    base_draw_prob = 0.27  # Base draw probability
    elo_closeness_factor = max(0, 1 - abs(elo_diff) / 400)  # 0 to 1, higher when teams are close
    draw_prob = base_draw_prob + (0.08 * elo_closeness_factor)  # Range: 0.27 to 0.35
    
    # Normalize probabilities to sum to 1
    total_prob = home_win_prob + away_win_prob + draw_prob
    home_win_prob /= total_prob
    away_win_prob /= total_prob
    draw_prob /= total_prob
    
    return {
        "home_win": home_win_prob,
        "draw": draw_prob,
        "away_win": away_win_prob
    }


def calculate_hybrid_probabilities(elo_probs, market_probs):
    """
    Combine Elo-based probabilities with market (bookmaker) probabilities.
    Uses a 60/40 weighting (60% Elo, 40% Market) by default.
    
    Args:
        elo_probs (dict): {"home_win": float, "draw": float, "away_win": float}
        market_probs (dict): {"HOME_WIN": float, "DRAW": float, "AWAY_WIN": float}
        
    Returns:
        dict: {"home_win": float, "draw": float, "away_win": float}
    """
    if not elo_probs or not market_probs:
        return None
    
    # Normalize market probs keys to match Elo format
    market_home = market_probs.get("HOME_WIN", 0)
    market_draw = market_probs.get("DRAW", 0)
    market_away = market_probs.get("AWAY_WIN", 0)
    
    # Calculate weighted average (60% Elo + 40% Market)
    hybrid_home = (HYBRID_ELO_WEIGHT * elo_probs["home_win"]) + (HYBRID_MARKET_WEIGHT * market_home)
    hybrid_draw = (HYBRID_ELO_WEIGHT * elo_probs["draw"]) + (HYBRID_MARKET_WEIGHT * market_draw)
    hybrid_away = (HYBRID_ELO_WEIGHT * elo_probs["away_win"]) + (HYBRID_MARKET_WEIGHT * market_away)
    
    # Normalize to ensure probabilities sum to 1
    total = hybrid_home + hybrid_draw + hybrid_away
    if total > 0:
        hybrid_home /= total
        hybrid_draw /= total
        hybrid_away /= total
    
    return {
        "home_win": hybrid_home,
        "draw": hybrid_draw,
        "away_win": hybrid_away
    }


def detect_value_bets(elo_probs, market_probs, threshold=0.10):
    """
    Detect value betting opportunities where Elo and market probabilities diverge significantly.
    
    Args:
        elo_probs (dict): Elo-based probabilities
        market_probs (dict): Market-based probabilities
        threshold (float): Minimum probability difference to flag as value bet (default: 10%)
        
    Returns:
        list: List of value bet opportunities with details
    """
    if not elo_probs or not market_probs:
        return []
    
    value_bets = []
    
    outcomes = [
        ("home_win", "HOME_WIN", "Home Win"),
        ("draw", "DRAW", "Draw"),
        ("away_win", "AWAY_WIN", "Away Win")
    ]
    
    for elo_key, market_key, outcome_name in outcomes:
        elo_prob = elo_probs.get(elo_key, 0)
        market_prob = market_probs.get(market_key, 0)
        diff = elo_prob - market_prob
        
        if abs(diff) >= threshold:
            value_bets.append({
                "outcome": outcome_name,
                "elo_prob": elo_prob * 100,  # Convert to percentage
                "market_prob": market_prob * 100,
                "difference": diff * 100,
                "direction": "overvalued" if diff > 0 else "undervalued",
                "confidence": "high" if abs(diff) >= 0.15 else "moderate"
            })
    
    return value_bets


if __name__ == "__main__":
    # Test the Elo client
    print("\n=== Testing Elo Rating Client ===\n")
    
    # Fetch all ratings
    ratings = fetch_team_elo_ratings()
    if ratings:
        print(f"\nSample Elo Ratings:")
        for team, elo in list(ratings.items())[:5]:
            print(f"  {team}: {elo:.1f}")
    
    # Test specific team lookup
    print("\n=== Testing Team Lookup ===")
    arsenal_elo = get_team_elo("Arsenal")
    if arsenal_elo:
        print(f"Arsenal Elo: {arsenal_elo:.1f}")
    
    # Test probability calculation
    if arsenal_elo:
        city_elo = get_team_elo("Manchester City")
        if city_elo:
            print(f"\n=== Testing Probability Calculation ===")
            print(f"Arsenal ({arsenal_elo:.1f}) vs Manchester City ({city_elo:.1f})")
            probs = calculate_elo_probabilities(arsenal_elo, city_elo)
            if probs:
                print(f"  Home Win: {probs['home_win']*100:.1f}%")
                print(f"  Draw: {probs['draw']*100:.1f}%")
                print(f"  Away Win: {probs['away_win']*100:.1f}%")
