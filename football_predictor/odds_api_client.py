import os
import re
from datetime import datetime, timedelta, timezone
import requests

from .config import API_MAX_RETRIES, API_TIMEOUT, setup_logger
from .constants import BASE_URL, LEAGUE_CODE_MAPPING
from .utils import create_retry_session, request_with_retries

API_KEYS = [
    os.environ.get("ODDS_API_KEY_1"),
    os.environ.get("ODDS_API_KEY_2"),
    os.environ.get("ODDS_API_KEY_3"),
    os.environ.get("ODDS_API_KEY_4"),
    os.environ.get("ODDS_API_KEY_5"),
    os.environ.get("ODDS_API_KEY_6"),
    os.environ.get("ODDS_API_KEY_7")
]
API_KEYS = [key for key in API_KEYS if key]
invalid_keys = set()  # Track invalid keys to skip them
current_key_index = 0

logger = setup_logger(__name__)

STATUS_FORCELIST = (429, 500, 502, 503, 504)
BACKOFF_FACTOR = 0.5

_session = create_retry_session(
    max_retries=API_MAX_RETRIES,
    backoff_factor=BACKOFF_FACTOR,
    status_forcelist=STATUS_FORCELIST,
)

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
        response = request_with_retries(
            _session,
            "GET",
            url,
            params={"apiKey": api_key},
            timeout=API_TIMEOUT,
            max_retries=API_MAX_RETRIES,
            backoff_factor=BACKOFF_FACTOR,
            status_forcelist=STATUS_FORCELIST,
            logger=logger,
            context="Odds API call",
            sanitize=sanitize_error_message,
        )
        return response.json()
    except requests.exceptions.RequestException as e:
        error_msg = sanitize_error_message(str(e))
        logger.error("Failed to fetch available sports: %s", error_msg)
        raise OddsAPIError(f"Error fetching sports: {error_msg}")

def get_odds_for_sport(sport_key, regions="us,uk,eu", markets="h2h", odds_format="decimal"):
    global invalid_keys
    url = f"{BASE_URL}/sports/{sport_key}/odds"
    
    # Get valid keys (excluding known invalid ones)
    valid_keys = [k for k in API_KEYS if k not in invalid_keys]
    
    if not valid_keys:
        raise OddsAPIError("All API keys are invalid. Please check your ODDS_API_KEY configurations.")
    
    # Try each valid key until one works
    last_error = None
    for attempt, api_key in enumerate(valid_keys):
        params = {
            "apiKey": api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format
        }
        
        try:
            response = request_with_retries(
                _session,
                "GET",
                url,
                params=params,
                timeout=API_TIMEOUT,
                max_retries=API_MAX_RETRIES,
                backoff_factor=BACKOFF_FACTOR,
                status_forcelist=STATUS_FORCELIST,
                logger=logger,
                context=f"Odds API call for {sport_key}",
                sanitize=sanitize_error_message,
            )
            data = response.json()

            quota_remaining = response.headers.get('x-requests-remaining', 'unknown')
            quota_used = response.headers.get('x-requests-used', 'unknown')
            logger.info(
                "📊 Odds API quota: %s remaining, %s used",
                quota_remaining,
                quota_used,
            )
            
            return data
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                # Invalid/expired key - mark it and try next
                invalid_keys.add(api_key)
                key_position = attempt + 1
                total_keys = len(valid_keys)
                logger.warning(
                    "❌ API key #%d/%d validation failed - trying alternate key...",
                    key_position,
                    total_keys,
                )
                last_error = e
                continue
            else:
                error_msg = sanitize_error_message(str(e))
                logger.error("Failed odds fetch for %s: %s", sport_key, error_msg)
                raise OddsAPIError(f"Error fetching odds for {sport_key}: {error_msg}")
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(
                "Retryable error with key %s for %s: %s",
                api_key,
                sport_key,
                sanitize_error_message(str(e)),
            )
            continue
    
    # If we get here, all keys failed
    error_msg = sanitize_error_message(str(last_error)) if last_error else "All API keys exhausted"
    raise OddsAPIError(f"Error fetching odds for {sport_key}: {error_msg}")

def get_upcoming_matches_with_odds(league_codes=None, next_n_days=7):
    if league_codes is None:
        league_codes = list(LEAGUE_CODE_MAPPING.keys())
    
    all_matches = []
    
    for league_code in league_codes:
        sport_key = LEAGUE_CODE_MAPPING.get(league_code)
        if not sport_key:
            logger.warning("⚠️  League code %s not mapped to Odds API sport key", league_code)
            continue

        try:
            logger.info("🔍 Fetching odds for %s (%s)...", league_code, sport_key)
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
                    "league_code": league_code,  # Store the code for API calls
                    "home_team": event['home_team'],
                    "away_team": event['away_team'],
                    "commence_time": event['commence_time'],
                    "bookmakers": event.get('bookmakers', [])
                }
                
                all_matches.append(match)
            
            league_matches = len([m for m in all_matches if m['sport_key'] == sport_key])
            logger.info("✅ Found %d matches for %s", league_matches, league_code)

        except OddsAPIError as e:
            error_msg = sanitize_error_message(str(e))
            logger.warning("⚠️  Error fetching %s: %s", league_code, error_msg)
            continue
        except Exception as e:
            error_msg = sanitize_error_message(str(e))
            logger.error("⚠️  Unexpected error for %s: %s", league_code, error_msg)
            continue
    
    if not all_matches:
        raise OddsAPIError("No matches with odds found")
    
    all_matches.sort(key=lambda x: x['commence_time'])
    return all_matches

def get_event_odds(sport_key, event_id, regions="us,uk,eu", markets="h2h"):
    global invalid_keys
    url = f"{BASE_URL}/sports/{sport_key}/events/{event_id}/odds"
    
    # Get valid keys (excluding known invalid ones)
    valid_keys = [k for k in API_KEYS if k not in invalid_keys]
    
    if not valid_keys:
        raise OddsAPIError("All API keys are invalid. Please check your ODDS_API_KEY configurations.")
    
    # Try each valid key until one works
    last_error = None
    for attempt, api_key in enumerate(valid_keys):
        params = {
            "apiKey": api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal"
        }
        
        try:
            response = request_with_retries(
                _session,
                "GET",
                url,
                params=params,
                timeout=API_TIMEOUT,
                max_retries=API_MAX_RETRIES,
                backoff_factor=BACKOFF_FACTOR,
                status_forcelist=STATUS_FORCELIST,
                logger=logger,
                context=f"Event odds call for {sport_key}",
                sanitize=sanitize_error_message,
            )
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                # Invalid/expired key - mark it and try next
                invalid_keys.add(api_key)
                key_position = attempt + 1
                total_keys = len(valid_keys)
                logger.warning(
                    "❌ API key #%d/%d validation failed for event odds - trying alternate key...",
                    key_position,
                    total_keys,
                )
                last_error = e
                continue
            else:
                error_msg = sanitize_error_message(str(e))
                logger.error("Failed event odds fetch for %s: %s", sport_key, error_msg)
                raise OddsAPIError(f"Error fetching event odds: {error_msg}")
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(
                "Retryable error retrieving event odds for %s with key %s: %s",
                sport_key,
                api_key,
                sanitize_error_message(str(e)),
            )
            continue
    
    # If we get here, all keys failed
    error_msg = sanitize_error_message(str(last_error)) if last_error else "All API keys exhausted"
    raise OddsAPIError(f"Error fetching event odds: {error_msg}")
