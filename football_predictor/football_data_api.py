import requests
import os
import re
from datetime import datetime, timedelta
import time
import random

class RateLimitExceededError(Exception):
    """Custom exception for API rate limit exceeded errors."""

def sanitize_error_message(message):
    """
    Remove API keys from error messages to prevent security leaks.
    Handles patterns: apiKey=XXX, X-Auth-Token: XXX
    Supports alphanumeric keys plus common special chars (., -, _)
    """
    if not message:
        return message
    
    # Remove API keys from query parameters (broader character set)
    sanitized = re.sub(r'apiKey=[A-Za-z0-9._-]+', 'apiKey=***', str(message))
    # Remove X-Auth-Token headers (broader character set)
    sanitized = re.sub(r'X-Auth-Token[:\s]+[A-Za-z0-9._-]+', 'X-Auth-Token: ***', sanitized)
    
    return sanitized

# API credentials for football-data.org from environment
API_KEYS = [
    os.environ.get("FOOTBALL_DATA_API_KEY_1"),
    os.environ.get("FOOTBALL_DATA_API_KEY_2"),
    os.environ.get("FOOTBALL_DATA_API_KEY_3")
]
# Filter out None values
API_KEYS = [key for key in API_KEYS if key is not None]
BASE_URL = "https://api.football-data.org/v4/"

# Global variable to track the current API key index
current_api_key_index = 0

def _get_next_api_key():
    global current_api_key_index
    key = API_KEYS[current_api_key_index]
    current_api_key_index = (current_api_key_index + 1) % len(API_KEYS)
    return key

def _make_api_request(endpoint, params=None):
    max_retries = 5
    retries = 0
    
    while retries < max_retries:
        api_key = _get_next_api_key()
        headers = {
            "X-Auth-Token": api_key
        }
        try:
            response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, params=params)
            response.raise_for_status()  # Raise an exception for HTTP errors
            time.sleep(1) # Add a 1-second delay between API calls to avoid rate limiting
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 429:
                    print(f"⏳ Rate limit hit for {endpoint}, retrying after {e.response.headers.get('Retry-After', 5)}s...")
                    retry_after = int(e.response.headers.get("Retry-After", 5)) # Default to 5 seconds
                    time.sleep(retry_after)
                    retries += 1
                elif e.response.status_code == 403:
                    print(f"🔑 403 Forbidden for {endpoint}, switching API key...")
                    retries += 1 # Increment retries, but switch key immediately
                else:
                    error_msg = sanitize_error_message(str(e))
                    print(f"❌ football-data.org error for {endpoint}: HTTP {e.response.status_code} - {error_msg}")
                    return None
            else:
                error_msg = sanitize_error_message(str(e))
                print(f"❌ football-data.org connection error for {endpoint}: {error_msg}")
                return None

    raise RateLimitExceededError(f"Rate limit exceeded for {endpoint} after {max_retries} retries.")

def get_competitions():
    data = _make_api_request("competitions")
    if data and "competitions" in data:
        return [{
            "id": comp["id"],
            "name": comp["name"],
            "code": comp["code"],
            "area": comp["area"]["name"]
        } for comp in data["competitions"]]
    return []

def get_seasons(competition_id):
    data = _make_api_request(f"competitions/{competition_id}")
    if data and "seasons" in data:
        return sorted([int(s["startDate"].split("-")[0]) for s in data["seasons"]], reverse=True)
    return []

def get_upcoming_matches(competition_id, next_n_days=7):
    """
    Get upcoming matches for a competition.
    competition_id can be either a numeric ID (e.g., 2021) or a code (e.g., 'PL')
    """
    today = datetime.now().date()
    future_date_limit = today + timedelta(days=next_n_days)

    params = {
        "dateFrom": today.strftime("%Y-%m-%d"),
        "dateTo": future_date_limit.strftime("%Y-%m-%d"),
        "status": "SCHEDULED,TIMED,POSTPONED"
    }

    data = _make_api_request(f"competitions/{competition_id}/matches", params=params)
    if data and "matches" in data:
        matches = []
        for match in data["matches"]:
            match_info = {
                "id": match["id"],
                "date": match["utcDate"],
                "timestamp": datetime.strptime(match["utcDate"], "%Y-%m-%dT%H:%M:%SZ").timestamp(),
                "home_team": match["homeTeam"]["name"],
                "away_team": match["awayTeam"]["name"],
                "league": match["competition"]["name"],
                "status": match["status"],
                "venue": "Unknown"
            }
            matches.append(match_info)
        return matches
    return []

def get_match_details(match_id):
    data = _make_api_request(f"matches/{match_id}")
    
    if data and "id" in data:
        # API returns match data directly, not wrapped in "match" key
        match = data
        match_info = {
            "id": match["id"],
            "date": match["utcDate"],
            "timestamp": datetime.strptime(match["utcDate"], "%Y-%m-%dT%H:%M:%SZ").timestamp(),
            "home_team": {"name": match["homeTeam"]["name"]},
            "away_team": {"name": match["awayTeam"]["name"]},
            "league": match["competition"]["name"],
            "status": match["status"],
            "venue": match.get("venue", "Unknown"),
            "goals": {
                "home": match["score"]["fullTime"]["home"] if match["score"]["fullTime"]["home"] is not None else match["score"]["halfTime"]["home"],
                "away": match["score"]["fullTime"]["away"] if match["score"]["fullTime"]["away"] is not None else match["score"]["halfTime"]["away"]
            },
            "score": {
                "fulltime": {
                    "home": match["score"]["fullTime"]["home"],
                    "away": match["score"]["fullTime"]["away"]
                }
            }
        }
        return match_info
    return None

def get_league_standings(competition_id):
    """
    Get current league standings for a competition.
    competition_id can be either a numeric ID or a code (e.g., 'PL')
    """
    data = _make_api_request(f"competitions/{competition_id}/standings")
    
    if data and "standings" in data:
        standings_list = []
        for standing in data["standings"]:
            if standing["type"] == "TOTAL":
                for team in standing["table"]:
                    team_info = {
                        "position": team["position"],
                        "name": team["team"]["name"],
                        "points": team["points"],
                        "played": team["playedGames"],
                        "won": team["won"],
                        "draw": team["draw"],
                        "lost": team["lost"],
                        "goals_for": team["goalsFor"],
                        "goals_against": team["goalsAgainst"],
                        "goal_difference": team["goalDifference"],
                        "form": team.get("form", "")
                    }
                    standings_list.append(team_info)
                return standings_list
    return []

def get_flashscore_upcoming_matches(next_n_days=7):
    print("Flashscore integration is temporarily commented out due to browser dependency.")
    return []

if __name__ == "__main__":

    competitions = get_competitions()
    if competitions:

        for comp in competitions:

            upcoming_matches = get_upcoming_matches(comp['id'], next_n_days=30)
            if upcoming_matches:
                for match in upcoming_matches[:5]:
                    pass
    
    # Flashscore integration is temporarily commented out
    # flashscore_matches = get_flashscore_upcoming_matches(next_n_days=7)
    # if flashscore_matches:
    #     for match in flashscore_matches[:5]:
    #         pass



