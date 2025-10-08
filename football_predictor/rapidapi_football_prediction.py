
import requests
import os
from datetime import datetime, timedelta

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
RAPIDAPI_HOST = "football-prediction-api.p.rapidapi.com"

class RapidAPIPredictionError(Exception):
    """Custom exception for RapidAPI prediction errors."""
    pass

def get_predictions_by_date(iso_date: str, federation: str = "UEFA", market: str = "classic") -> dict:
    """Fetches predictions for matches on a specific date.
    
    Args:
        iso_date: Date in ISO format (YYYY-MM-DD)
        federation: Federation filter (UEFA, CONMEBOL, AFC, CAF, CONCACAF, OFC)
        market: Prediction market (classic, over_25, btts, etc.)
    
    Returns:
        Dictionary containing match predictions
    
    Raises:
        RapidAPIPredictionError: If the API call fails
    """
    if not RAPIDAPI_KEY:
        raise RapidAPIPredictionError("RAPIDAPI_KEY environment variable not set.")
    
    url = f"https://{RAPIDAPI_HOST}/api/v2/predictions"
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }
    
    params = {
        "iso_date": iso_date,
        "federation": federation,
        "market": market
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "error":
            raise RapidAPIPredictionError(f"RapidAPI returned an error: {data.get('message', 'Unknown error')}")
        
        return data
    except requests.exceptions.Timeout:
        raise RapidAPIPredictionError("RapidAPI request timed out")
    except requests.exceptions.RequestException as e:
        raise RapidAPIPredictionError(f"Error fetching predictions from RapidAPI: {e}")

def get_upcoming_matches_with_predictions(next_n_days: int = 7, federation: str = "UEFA") -> list:
    """Fetches upcoming matches with predictions from RapidAPI.
    
    Args:
        next_n_days: Number of days to look ahead (max 7 to avoid long wait times)
        federation: Federation to filter by (UEFA, CONMEBOL, AFC, CAF, CONCACAF, OFC)
    
    Returns:
        List of matches with predictions
    """
    if not RAPIDAPI_KEY:
        raise RapidAPIPredictionError("RAPIDAPI_KEY environment variable not set.")
    
    all_matches = []
    today = datetime.now().date()
    consecutive_failures = 0
    max_consecutive_failures = 3
    
    # Limit days to check to avoid long wait times
    days_to_check = min(next_n_days, 7)
    
    # Fetch predictions for each day in the range
    for day_offset in range(days_to_check):
        target_date = today + timedelta(days=day_offset)
        iso_date = target_date.isoformat()
        
        try:
            response = get_predictions_by_date(iso_date, federation, market="classic")
            
            if "data" in response and response["data"]:
                consecutive_failures = 0  # Reset on success
                for match in response["data"]:
                    # Parse the start_date to get timestamp
                    try:
                        start_datetime = datetime.fromisoformat(match.get("start_date", "").replace("Z", "+00:00"))
                        timestamp = start_datetime.timestamp()
                        datetime_str = start_datetime.strftime("%Y-%m-%d %H:%M")
                    except:
                        timestamp = 0
                        datetime_str = match.get("start_date", "")
                    
                    # Normalize the match data to our format
                    normalized_match = {
                        "id": match.get("id"),
                        "home_team": match.get("home_team"),
                        "away_team": match.get("away_team"),
                        "league": match.get("competition_name", "Unknown"),
                        "date": match.get("start_date"),
                        "timestamp": timestamp,
                        "status": "SCHEDULED",
                        "venue": "Unknown",
                        "datetime": datetime_str,
                        "predictions": {
                            "1x2": {
                                "prediction": match.get("prediction"),
                                "confidence": match.get("confidence"),
                                "probabilities": match.get("probabilities", {}),
                                "is_safe_bet": match.get("confidence", 0) > 0.7
                            },
                            "odds": match.get("odds", {}),
                            "over_under": {},
                            "exact_score": {}
                        }
                    }
                    all_matches.append(normalized_match)
            else:
                consecutive_failures += 1
                    
        except RapidAPIPredictionError as e:
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                print(f"❌ Too many consecutive failures, stopping RapidAPI checks")
                raise RapidAPIPredictionError("RapidAPI service unavailable or no predictions available")
            continue
        except Exception as e:
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                print(f"❌ Too many consecutive failures, stopping RapidAPI checks")
                raise
            continue
    
    if not all_matches:
        raise RapidAPIPredictionError("No matches with predictions found in RapidAPI")
    
    return all_matches
