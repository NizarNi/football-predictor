import requests
import os
from datetime import datetime, timedelta, timezone

API_KEYS = [
    os.environ.get("ODDS_API_KEY_1"),
    os.environ.get("ODDS_API_KEY_2"),
    os.environ.get("ODDS_API_KEY_3"),
    os.environ.get("ODDS_API_KEY_4")
]
API_KEYS = [key for key in API_KEYS if key]
invalid_keys = set()  # Track invalid keys to skip them

BASE_URL = "https://api.the-odds-api.com/v4"
current_key_index = 0

LEAGUE_CODE_MAPPING = {
    "PL": "soccer_epl",
    "PD": "soccer_spain_la_liga",
    "BL1": "soccer_germany_bundesliga",
    "SA": "soccer_italy_serie_a",
    "FL1": "soccer_france_ligue_one",
    "CL": "soccer_uefa_champs_league",
    "EL": "soccer_uefa_europa_league"
}

class OddsAPIError(Exception):
    pass

def get_next_api_key():
    global current_key_index
    if not API_KEYS:
        raise OddsAPIError("No ODDS_API_KEY environment variables set.")
    
    key = API_KEYS[current_key_index]
    current_key_index = (current_key_index + 1) % len(API_KEYS)
    return key

def get_available_sports():
    api_key = get_next_api_key()
    url = f"{BASE_URL}/sports/"
    
    try:
        response = requests.get(url, params={"apiKey": api_key}, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise OddsAPIError(f"Error fetching sports: {e}")

def get_odds_for_sport(sport_key, regions="us,uk,eu", markets="h2h", odds_format="decimal"):
    api_key = get_next_api_key()
    url = f"{BASE_URL}/sports/{sport_key}/odds"
    
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": odds_format
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        quota_remaining = response.headers.get('x-requests-remaining', 'unknown')
        quota_used = response.headers.get('x-requests-used', 'unknown')
        print(f"📊 Odds API quota: {quota_remaining} remaining, {quota_used} used")
        
        return data
    except requests.exceptions.RequestException as e:
        raise OddsAPIError(f"Error fetching odds for {sport_key}: {e}")

def get_upcoming_matches_with_odds(league_codes=None, next_n_days=7):
    if league_codes is None:
        league_codes = list(LEAGUE_CODE_MAPPING.keys())
    
    all_matches = []
    
    for league_code in league_codes:
        sport_key = LEAGUE_CODE_MAPPING.get(league_code)
        if not sport_key:
            print(f"⚠️  League code {league_code} not mapped to Odds API sport key")
            continue
        
        try:
            print(f"🔍 Fetching odds for {league_code} ({sport_key})...")
            odds_data = get_odds_for_sport(sport_key, regions="us,uk,eu", markets="h2h")
            
            cutoff_time = datetime.now(timezone.utc) + timedelta(days=next_n_days)
            
            for event in odds_data:
                commence_time = datetime.fromisoformat(event['commence_time'].replace('Z', '+00:00'))
                
                if commence_time > cutoff_time:
                    continue
                
                match = {
                    "id": hash(event['id']),
                    "event_id": event['id'],
                    "sport_key": event['sport_key'],
                    "league": event.get('sport_title', league_code),
                    "home_team": event['home_team'],
                    "away_team": event['away_team'],
                    "commence_time": event['commence_time'],
                    "bookmakers": event.get('bookmakers', [])
                }
                
                all_matches.append(match)
            
            print(f"✅ Found {len([m for m in all_matches if m['sport_key'] == sport_key])} matches for {league_code}")
            
        except OddsAPIError as e:
            print(f"⚠️  Error fetching {league_code}: {e}")
            continue
        except Exception as e:
            print(f"⚠️  Unexpected error for {league_code}: {e}")
            continue
    
    if not all_matches:
        raise OddsAPIError("No matches with odds found")
    
    all_matches.sort(key=lambda x: x['commence_time'])
    return all_matches

def get_event_odds(sport_key, event_id, regions="us,uk,eu", markets="h2h"):
    api_key = get_next_api_key()
    url = f"{BASE_URL}/sports/{sport_key}/events/{event_id}/odds"
    
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal"
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise OddsAPIError(f"Error fetching event odds: {e}")
