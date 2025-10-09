import requests
import os
from datetime import datetime

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
RAPIDAPI_HOST = "api-football-v1.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}/v3"

# Map league codes to API-Football league IDs
LEAGUE_ID_MAP = {
    "PL": 39,      # Premier League
    "PD": 140,     # La Liga
    "BL1": 78,     # Bundesliga
    "SA": 135,     # Serie A
    "FL1": 61,     # Ligue 1
    "CL": 2,       # Champions League
    "EL": 3        # Europa League
}

def get_current_season():
    """Get current season year (start year of season, e.g., 2024 for 2024-25 season)"""
    # RapidAPI may not have future seasons, so default to 2024 for now
    # This can be updated when 2025 season data becomes available
    return 2024

def fetch_standings_from_rapidapi(league_code, season=None):
    """
    Fetch league standings from RapidAPI (API-Football)
    
    Args:
        league_code: League code (PL, PD, BL1, SA, FL1, CL, EL)
        season: Season year (optional, defaults to current season)
    
    Returns:
        list: Standings data in format compatible with football-data.org
    """
    if league_code not in LEAGUE_ID_MAP:
        print(f"⚠️  League {league_code} not supported in RapidAPI")
        return []
    
    if season is None:
        season = get_current_season()
    
    league_id = LEAGUE_ID_MAP[league_code]
    
    try:
        print(f"📊 Fetching RapidAPI standings for {league_code} (league_id={league_id}, season={season})...")
        
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST
        }
        
        params = {
            "league": league_id,
            "season": season
        }
        
        response = requests.get(f"{BASE_URL}/standings", headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("response") and len(data["response"]) > 0:
            standings_data = data["response"][0]["league"]["standings"][0]
            
            # Convert to football-data.org format
            standings = []
            for team in standings_data:
                standings.append({
                    "name": team["team"]["name"],
                    "position": team["rank"],
                    "points": team["points"],
                    "played": team["all"]["played"],
                    "won": team["all"]["win"],
                    "draw": team["all"]["draw"],
                    "lost": team["all"]["lose"],
                    "goals_for": team["all"]["goals"]["for"],
                    "goals_against": team["all"]["goals"]["against"],
                    "goal_difference": team["goalsDiff"],
                    "form": team.get("form", "")  # Last 5 results: W/D/L
                })
            
            print(f"✅ Retrieved {len(standings)} teams from RapidAPI")
            return standings
        else:
            print(f"⚠️  No standings data from RapidAPI for {league_code}")
            return []
            
    except requests.exceptions.Timeout:
        print(f"⏳ RapidAPI request timed out for {league_code}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"❌ RapidAPI error for {league_code}: {str(e)}")
        return []
    except Exception as e:
        print(f"❌ Error processing RapidAPI data for {league_code}: {str(e)}")
        return []
