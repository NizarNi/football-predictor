import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

from config import (
    API_TIMEOUT_ODDS,
    DEFAULT_ODDS_MARKETS,
    DEFAULT_ODDS_REGIONS,
    LEAGUE_CODE_MAPPING,
    ODDS_INVALID_KEY_TTL_DAYS,
    ODDS_INVALID_KEYS_PATH,
)

logger = logging.getLogger(__name__)

API_KEYS: List[Optional[str]] = [
    os.environ.get("ODDS_API_KEY_1"),
    os.environ.get("ODDS_API_KEY_2"),
    os.environ.get("ODDS_API_KEY_3"),
    os.environ.get("ODDS_API_KEY_4"),
    os.environ.get("ODDS_API_KEY_5"),
    os.environ.get("ODDS_API_KEY_6"),
    os.environ.get("ODDS_API_KEY_7"),
]
API_KEYS = [key for key in API_KEYS if key]

BASE_URL = "https://api.the-odds-api.com/v4"

_api_key_lock = threading.Lock()
_invalid_keys_lock = threading.Lock()
current_key_index = 0


def _load_invalid_keys() -> Dict[str, datetime]:
    if not ODDS_INVALID_KEYS_PATH.exists():
        return {}

    try:
        with ODDS_INVALID_KEYS_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Unable to read cached invalid Odds API keys: %s", exc)
        return {}

    now = datetime.now(timezone.utc)

    if isinstance(data, dict):
        entries = data.get("keys", [])
        invalid: Dict[str, datetime] = {}
        changed = False

        for item in entries:
            if not isinstance(item, dict):
                changed = True
                continue

            key = item.get("key")
            expires_at = item.get("expires_at")

            if not key or not isinstance(key, str):
                changed = True
                continue

            if not expires_at or not isinstance(expires_at, str):
                changed = True
                continue

            try:
                expiry = datetime.fromisoformat(expires_at)
            except ValueError:
                changed = True
                continue

            if expiry <= now:
                changed = True
                continue

            invalid[key] = expiry

        if changed:
            _persist_invalid_keys_locked(invalid)

        return invalid

    if isinstance(data, list):
        logger.info("Clearing legacy invalid key cache to allow renewed Odds API keys")
        try:
            ODDS_INVALID_KEYS_PATH.unlink()
        except OSError:
            logger.debug("Failed to remove legacy invalid key cache", exc_info=True)
        return {}

    return {}


def _persist_invalid_keys_locked(invalid_keys: Dict[str, datetime]) -> None:
    try:
        with ODDS_INVALID_KEYS_PATH.open("w", encoding="utf-8") as fh:
            payload = {
                "version": 1,
                "keys": [
                    {
                        "key": key,
                        "expires_at": expiry.astimezone(timezone.utc).isoformat(),
                    }
                    for key, expiry in sorted(invalid_keys.items())
                ],
            }
            json.dump(payload, fh)
    except OSError as exc:
        logger.warning("Unable to persist invalid Odds API keys: %s", exc)


def _prune_expired_locked(now: Optional[datetime] = None) -> None:
    if now is None:
        now = datetime.now(timezone.utc)

    expired = [key for key, expiry in invalid_key_metadata.items() if expiry <= now]

    if not expired:
        return

    for key in expired:
        invalid_key_metadata.pop(key, None)

    _persist_invalid_keys_locked(invalid_key_metadata)


def _mark_key_invalid(api_key: str) -> None:
    expiry = datetime.now(timezone.utc) + timedelta(days=ODDS_INVALID_KEY_TTL_DAYS)

    with _invalid_keys_lock:
        _prune_expired_locked(now=datetime.now(timezone.utc))
        invalid_key_metadata[api_key] = expiry
        _persist_invalid_keys_locked(invalid_key_metadata)
        logger.info(
            "Flagged Odds API key ending %s as invalid until %s",
            api_key[-4:],
            expiry.date(),
        )


def _valid_api_keys() -> List[str]:
    with _invalid_keys_lock:
        _prune_expired_locked(now=datetime.now(timezone.utc))
        return [k for k in API_KEYS if k not in invalid_key_metadata]


invalid_key_metadata: Dict[str, datetime] = _load_invalid_keys()

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
    """Domain-specific error emitted for Odds API failures."""

    pass

def get_next_api_key() -> str:
    global current_key_index

    if not API_KEYS:
        raise OddsAPIError("No ODDS_API_KEY environment variables set.")

    with _api_key_lock:
        available_keys = len(API_KEYS)
        if available_keys == 0:
            raise OddsAPIError("No ODDS_API_KEY environment variables set.")

        for _ in range(available_keys):
            key = API_KEYS[current_key_index]
            current_key_index = (current_key_index + 1) % available_keys
            with _invalid_keys_lock:
                _prune_expired_locked(now=datetime.now(timezone.utc))
                if key not in invalid_key_metadata:
                    return key

    raise OddsAPIError("All configured Odds API keys are marked invalid. Please update credentials.")

def get_available_sports():
    api_key = get_next_api_key()
    url = f"{BASE_URL}/sports/"

    try:
        response = requests.get(url, params={"apiKey": api_key}, timeout=API_TIMEOUT_ODDS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        error_msg = sanitize_error_message(str(e))
        raise OddsAPIError(f"Error fetching sports: {error_msg}")

def get_odds_for_sport(
    sport_key: str,
    regions: str = DEFAULT_ODDS_REGIONS,
    markets: str = DEFAULT_ODDS_MARKETS,
    odds_format: str = "decimal",
):
    url = f"{BASE_URL}/sports/{sport_key}/odds"

    # Get valid keys (excluding known invalid ones)
    valid_keys = _valid_api_keys()

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
            response = requests.get(url, params=params, timeout=API_TIMEOUT_ODDS)
            response.raise_for_status()
            data = response.json()

            quota_remaining = response.headers.get('x-requests-remaining', 'unknown')
            quota_used = response.headers.get('x-requests-used', 'unknown')
            logger.info(
                "Odds API quota status for %s: %s remaining / %s used",
                sport_key,
                quota_remaining,
                quota_used,
            )

            return data
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                # Invalid/expired key - mark it and try next
                _mark_key_invalid(api_key)
                key_position = attempt + 1
                total_keys = len(valid_keys)
                logger.warning(
                    "Odds API key %s/%s rejected with 401 - rotating to next key",
                    key_position,
                    total_keys,
                )
                last_error = e
                continue
            else:
                error_msg = sanitize_error_message(str(e))
                raise OddsAPIError(f"Error fetching odds for {sport_key}: {error_msg}")
        except requests.exceptions.RequestException as e:
            last_error = e
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
            logger.warning("League code %s not mapped to Odds API sport key", league_code)
            continue

        try:
            logger.info("Fetching odds for %s (%s)", league_code, sport_key)
            odds_data = get_odds_for_sport(sport_key, regions=DEFAULT_ODDS_REGIONS, markets=DEFAULT_ODDS_MARKETS)

            cutoff_time = datetime.now(timezone.utc) + timedelta(days=next_n_days)

            for event in odds_data:
                commence_time = datetime.fromisoformat(event['commence_time'].replace('Z', '+00:00'))

                if commence_time > cutoff_time:
                    continue

                match = {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"odds-event:{event['id']}")),
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
            
            logger.info(
                "Found %s matches for %s",
                len([m for m in all_matches if m['sport_key'] == sport_key]),
                league_code,
            )

        except OddsAPIError as e:
            error_msg = sanitize_error_message(str(e))
            logger.warning("Error fetching odds for %s: %s", league_code, error_msg)
            continue
        except Exception as e:
            error_msg = sanitize_error_message(str(e))
            logger.exception("Unexpected error fetching odds for %s: %s", league_code, error_msg)
            continue

    if not all_matches:
        raise OddsAPIError("No matches with odds found")

    all_matches.sort(key=lambda x: x['commence_time'])
    return all_matches

def get_event_odds(
    sport_key: str,
    event_id: str,
    regions: str = DEFAULT_ODDS_REGIONS,
    markets: str = DEFAULT_ODDS_MARKETS,
):
    url = f"{BASE_URL}/sports/{sport_key}/events/{event_id}/odds"

    # Get valid keys (excluding known invalid ones)
    valid_keys = _valid_api_keys()

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
            response = requests.get(url, params=params, timeout=API_TIMEOUT_ODDS)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                # Invalid/expired key - mark it and try next
                _mark_key_invalid(api_key)
                key_position = attempt + 1
                total_keys = len(valid_keys)
                logger.warning(
                    "Odds API key %s/%s rejected with 401 when fetching event %s - rotating",
                    key_position,
                    total_keys,
                    event_id,
                )
                last_error = e
                continue
            else:
                error_msg = sanitize_error_message(str(e))
                raise OddsAPIError(f"Error fetching event odds: {error_msg}")
        except requests.exceptions.RequestException as e:
            logger.warning(
                "Request error fetching event odds for %s (%s): %s",
                event_id,
                sport_key,
                sanitize_error_message(str(e)),
            )
            last_error = e
            continue

    # If we get here, all keys failed
    error_msg = sanitize_error_message(str(last_error)) if last_error else "All API keys exhausted"
    raise OddsAPIError(f"Error fetching event odds: {error_msg}")
