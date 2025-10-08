
import requests
import os
import json

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
RAPIDAPI_HOST = "football-prediction-api.p.rapidapi.com"

class RapidAPIPredictionError(Exception):
    """Custom exception for RapidAPI prediction errors."""
    pass

def get_rapidapi_predictions(match_id: str, market: str = "classic") -> dict:
    """Fetches predictions for a specific match from RapidAPI.

    Args:
        match_id: The ID of the match.
        market: The prediction market (e.g., "classic", "over_25").

    Returns:
        A dictionary containing the prediction data.

    Raises:
        RapidAPIPredictionError: If the API call fails or returns an error.
    """
    if not RAPIDAPI_KEY:
        raise RapidAPIPredictionError("RAPIDAPI_KEY environment variable not set.")

    url = f"https://{RAPIDAPI_HOST}/api/v2/predictions/match/{match_id}?market={market}"

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        if data.get("status") == "error":
            raise RapidAPIPredictionError(f"RapidAPI returned an error: {data.get('message', 'Unknown error')}")
        return data
    except requests.exceptions.RequestException as e:
        raise RapidAPIPredictionError(f"Error fetching prediction from RapidAPI: {e}")

def get_rapidapi_upcoming_matches(next_n_days: int = 7, leagues: list = None) -> list:
    """Fetches upcoming matches from RapidAPI for specified leagues.

    Args:
        next_n_days: Number of days in the future to fetch matches for.
        leagues: A list of league codes (e.g., ["PL", "CL"]).

    Returns:
        A list of dictionaries, each representing an upcoming match with predictions.

    Raises:
        RapidAPIPredictionError: If the API call fails or returns an error.
    """
    if not RAPIDAPI_KEY:
        raise RapidAPIPredictionError("RAPIDAPI_KEY environment variable not set.")

    # The RapidAPI documentation implies that the 'Predictions' endpoint is for a specific match_id.
    # There doesn't seem to be a direct 'upcoming matches' endpoint that takes league codes.
    # I will assume the user wants to fetch predictions for matches already obtained from football-data.org.
    # This function will be a placeholder or will need to be adapted if a suitable endpoint is found.
    # For now, I will focus on integrating the prediction logic for individual matches.
    print("Warning: get_rapidapi_upcoming_matches is a placeholder. RapidAPI primarily provides predictions for specific matches.")
    return []


