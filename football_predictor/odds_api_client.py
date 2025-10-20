import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Optional, Tuple

import requests

from .app_utils import AdaptiveTimeoutController
from .config import API_TIMEOUT, setup_logger
from .constants import BASE_URL, LEAGUE_CODE_MAPPING
from . import config as config_module
from .errors import APIError

API_KEYS = [
    os.environ.get("ODDS_API_KEY_1"),
    os.environ.get("ODDS_API_KEY_2"),
    os.environ.get("ODDS_API_KEY_3"),
    os.environ.get("ODDS_API_KEY_4"),
    os.environ.get("ODDS_API_KEY_5"),
    os.environ.get("ODDS_API_KEY_6"),
    os.environ.get("ODDS_API_KEY_7"),
    os.environ.get("ODDS_API_KEY_8")   
]
API_KEYS = [key for key in API_KEYS if key]
invalid_keys = set()  # Track invalid keys to skip them
current_key_index = 0

logger = setup_logger(__name__)
adaptive_timeout = AdaptiveTimeoutController(base_timeout=API_TIMEOUT, max_timeout=30)

MAX_RETRY_AFTER = 10.0

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _parse_retry_after_seconds(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None

    try:
        seconds = float(value)
    except (TypeError, ValueError):
        pass
    else:
        return max(0.0, min(seconds, MAX_RETRY_AFTER))

    try:
        dt = parsedate_to_datetime(value)
    except Exception:
        return None

    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(dt.tzinfo)
    delay = (dt - now).total_seconds()
    if delay > 0:
        delay = max(delay, 0.1)
    return max(0.0, min(delay, MAX_RETRY_AFTER))


def _get_retry_delay(attempt: int, response: Optional[requests.Response] = None) -> float:
    if response and "Retry-After" in response.headers:
        parsed = _parse_retry_after_seconds(response.headers.get("Retry-After"))
        if parsed is not None:
            return parsed

    base = config_module.ODDS_BASE_DELAY
    jitter = random.uniform(0, config_module.ODDS_JITTER)
    delay = base * (2 ** (attempt - 1)) + jitter
    return min(delay, MAX_RETRY_AFTER)


def fetch_odds_with_backoff(
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: Optional[float] = None,
    max_attempts: Optional[int] = None,
    request_callable: Optional[Callable[..., requests.Response]] = None,
) -> Tuple[requests.Response, int]:
    attempts = max_attempts or config_module.ODDS_MAX_ATTEMPTS
    timeout = timeout or API_TIMEOUT
    request_fn = request_callable or requests.get

    last_error: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        try:
            response = request_fn(url, headers=headers, params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
            if attempt == attempts:
                break
            delay = _get_retry_delay(attempt)
            logger.warning(
                "Odds API error %r, retrying in %.1fs (attempt %d/%d)",
                exc,
                delay,
                attempt,
                attempts,
            )
            time.sleep(delay)
            continue

        if response.status_code == 200:
            return response, attempt

        if response.status_code in TRANSIENT_STATUS_CODES:
            if attempt == attempts:
                break
            delay = _get_retry_delay(attempt, response)
            logger.warning(
                "Odds API transient %s, retrying in %.1fs (attempt %d/%d)",
                response.status_code,
                delay,
                attempt,
                attempts,
            )
            time.sleep(delay)
            continue

        try:
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - defensive
            last_error = exc
            raise

    error_message = "Odds API retry limit exceeded"
    if last_error is not None:
        error_message = f"{error_message}: {last_error}"
        error_code = "NETWORK_ERROR"
        if isinstance(last_error, requests.Timeout):
            error_code = "TIMEOUT"
        elif isinstance(last_error, requests.ConnectionError):
            error_code = "NETWORK_ERROR"
        raise APIError("OddsAPI", error_code, error_message) from last_error
    raise APIError("OddsAPI", "NETWORK_ERROR", error_message)


def request_with_retries(*args, **kwargs):
    """Temporary shim that delegates to :func:`fetch_odds_with_backoff`."""

    return fetch_odds_with_backoff(*args, **kwargs)[0]

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

def get_next_api_key():
    global current_key_index
    if not API_KEYS:
        raise APIError("OddsAPI", "CONFIG_ERROR", "No ODDS_API_KEY environment variables set.")
    
    key = API_KEYS[current_key_index]
    current_key_index = (current_key_index + 1) % len(API_KEYS)
    return key

def get_available_sports():
    api_key = get_next_api_key()
    url = f"{BASE_URL}/sports/"

    timeout = adaptive_timeout.get_timeout()
    try:
        response, attempts = fetch_odds_with_backoff(
            url,
            params={"apiKey": api_key},
            timeout=timeout,
        )
        setattr(response, "_odds_backoff_attempts", attempts)
        if attempts > 1:
            logger.info("Odds API backoff done for sports listing after %d attempts", attempts)
        adaptive_timeout.record_success()
    except requests.Timeout as exc:
        adaptive_timeout.record_failure()
        logger.warning("[Resilience] API timeout or network issue: %s", exc)
        logger.error("Failed to fetch available sports: request timed out")
        raise APIError("OddsAPI", "TIMEOUT", "The Odds API did not respond in time.") from exc
    except requests.ConnectionError as exc:
        adaptive_timeout.record_failure()
        logger.warning("[Resilience] API timeout or network issue: %s", exc)
        error_msg = sanitize_error_message(str(exc))
        logger.error("Failed to fetch available sports: %s", error_msg)
        raise APIError("OddsAPI", "NETWORK_ERROR", "A network error occurred.", error_msg) from exc
    except requests.RequestException as e:
        adaptive_timeout.record_failure()
        logger.warning("[Resilience] API request failure detected: %s", e)
        error_msg = sanitize_error_message(str(e))
        logger.error("Failed to fetch available sports: %s", error_msg)
        raise APIError("OddsAPI", "NETWORK_ERROR", "A network error occurred.", error_msg) from e
    except APIError as exc:
        adaptive_timeout.record_failure()
        sanitized = sanitize_error_message(exc.details or exc.message)
        if exc.code == "TIMEOUT":
            logger.warning("[Resilience] API timeout or network issue: %s", exc)
            logger.error("Failed to fetch available sports: request timed out")
            raise APIError("OddsAPI", "TIMEOUT", "The Odds API did not respond in time.") from exc
        if exc.code == "NETWORK_ERROR":
            logger.warning("[Resilience] API timeout or network issue: %s", exc)
            logger.error("Failed to fetch available sports: %s", sanitized)
            raise APIError("OddsAPI", "NETWORK_ERROR", "A network error occurred.", sanitized) from exc
        raise

    try:
        data = response.json()
        return data
    except ValueError as e:
        error_msg = sanitize_error_message(str(e))
        logger.error("Failed to parse available sports response: %s", error_msg)
        raise APIError("OddsAPI", "PARSE_ERROR", "Failed to parse API response.", error_msg) from e

def get_odds_for_sport(sport_key, regions="us,uk,eu", markets="h2h", odds_format="decimal"):
    global invalid_keys
    url = f"{BASE_URL}/sports/{sport_key}/odds"
    
    # Get valid keys (excluding known invalid ones)
    valid_keys = [k for k in API_KEYS if k not in invalid_keys]
    
    if not valid_keys:
        raise APIError(
            "OddsAPI",
            "AUTH_ERROR",
            "All API keys are invalid. Please check your ODDS_API_KEY configurations.",
        )

    # Try each valid key until one works
    last_error: Optional[APIError] = None
    for attempt, api_key in enumerate(valid_keys):
        params = {
            "apiKey": api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format
        }

        timeout = adaptive_timeout.get_timeout()
        try:
            response, attempts = fetch_odds_with_backoff(
                url,
                params=params,
                timeout=timeout,
            )
            setattr(response, "_odds_backoff_attempts", attempts)
            if attempts > 1:
                logger.info(
                    "Odds API backoff done for %s after %d attempts",
                    sport_key,
                    attempts,
                )
            adaptive_timeout.record_success()
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
                last_error = APIError(
                    "OddsAPI",
                    "AUTH_ERROR",
                    "The provided Odds API key was rejected.",
                )
                continue
            else:
                adaptive_timeout.record_failure()
                error_msg = sanitize_error_message(str(e))
                logger.error("Failed odds fetch for %s: %s", sport_key, error_msg)
                raise APIError(
                    "OddsAPI",
                    "HTTP_ERROR",
                    f"Error fetching odds for {sport_key}.",
                    error_msg,
                ) from e
        except requests.Timeout as exc:
            adaptive_timeout.record_failure()
            logger.warning("[Resilience] API timeout or network issue: %s", exc)
            logger.warning(
                "Timeout retrieving odds for %s with key %s", sport_key, api_key
            )
            last_error = APIError(
                "OddsAPI",
                "TIMEOUT",
                "The Odds API did not respond in time.",
            )
            continue
        except requests.ConnectionError as exc:
            adaptive_timeout.record_failure()
            sanitized_error = sanitize_error_message(str(exc))
            logger.warning("[Resilience] API timeout or network issue: %s", exc)
            logger.warning(
                "Retryable error with key %s for %s: %s",
                api_key,
                sport_key,
                sanitized_error,
            )
            last_error = APIError(
                "OddsAPI",
                "NETWORK_ERROR",
                "A network error occurred.",
                sanitized_error,
            )
            continue
        except requests.RequestException as e:
            adaptive_timeout.record_failure()
            logger.warning("[Resilience] API request failure detected: %s", e)
            sanitized_error = sanitize_error_message(str(e))
            logger.warning(
                "Retryable error with key %s for %s: %s",
                api_key,
                sport_key,
                sanitized_error,
            )
            last_error = APIError(
                "OddsAPI",
                "NETWORK_ERROR",
                "A network error occurred.",
                sanitized_error,
            )
            continue
        except APIError as exc:
            adaptive_timeout.record_failure()
            if exc.code not in {"TIMEOUT", "NETWORK_ERROR"}:
                raise
            sanitized_error = sanitize_error_message(exc.details or exc.message)
            logger.warning(
                "[Resilience] API timeout or network issue: %s",
                exc,
            )
            logger.warning(
                "Retryable error with key %s for %s: %s",
                api_key,
                sport_key,
                sanitized_error,
            )
            message = (
                "The Odds API did not respond in time."
                if exc.code == "TIMEOUT"
                else "A network error occurred."
            )
            details = None if exc.code == "TIMEOUT" else sanitized_error
            last_error = APIError("OddsAPI", exc.code, message, details)
            continue

        try:
            data = response.json()
        except ValueError as e:
            error_msg = sanitize_error_message(str(e))
            logger.error("Failed odds fetch for %s: %s", sport_key, error_msg)
            raise APIError(
                "OddsAPI",
                "PARSE_ERROR",
                "Failed to parse API response.",
                error_msg,
            ) from e

        quota_remaining = response.headers.get('x-requests-remaining', 'unknown')
        quota_used = response.headers.get('x-requests-used', 'unknown')
        logger.info(
            "📊 Odds API quota: %s remaining, %s used",
            quota_remaining,
            quota_used,
        )

        return data

    # If we get here, all keys failed
    if last_error is not None:
        raise last_error

    raise APIError(
        "OddsAPI",
        "NETWORK_ERROR",
        f"Error fetching odds for {sport_key}.",
    )

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

        except APIError as e:
            error_detail = e.details or e.message
            error_msg = sanitize_error_message(error_detail)
            logger.warning("⚠️  Error fetching %s: %s", league_code, error_msg)
            continue
        except Exception as e:
            error_msg = sanitize_error_message(str(e))
            logger.error("⚠️  Unexpected error for %s: %s", league_code, error_msg)
            continue

    if not all_matches:
        raise APIError("OddsAPI", "NO_DATA", "No matches with odds found.")
    
    all_matches.sort(key=lambda x: x['commence_time'])
    return all_matches

def get_event_odds(sport_key, event_id, regions="us,uk,eu", markets="h2h"):
    global invalid_keys
    url = f"{BASE_URL}/sports/{sport_key}/events/{event_id}/odds"
    
    # Get valid keys (excluding known invalid ones)
    valid_keys = [k for k in API_KEYS if k not in invalid_keys]
    
    if not valid_keys:
        raise APIError(
            "OddsAPI",
            "AUTH_ERROR",
            "All API keys are invalid. Please check your ODDS_API_KEY configurations.",
        )
    
    # Try each valid key until one works
    last_error: Optional[APIError] = None
    for attempt, api_key in enumerate(valid_keys):
        params = {
            "apiKey": api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal"
        }
        
        timeout = adaptive_timeout.get_timeout()
        try:
            response, attempts = fetch_odds_with_backoff(
                url,
                params=params,
                timeout=timeout,
            )
            setattr(response, "_odds_backoff_attempts", attempts)
            if attempts > 1:
                logger.info(
                    "Odds API backoff done for %s event %s after %d attempts",
                    sport_key,
                    event_id,
                    attempts,
                )
            adaptive_timeout.record_success()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                invalid_keys.add(api_key)
                key_position = attempt + 1
                total_keys = len(valid_keys)
                logger.warning(
                    "❌ API key #%d/%d validation failed for event odds - trying alternate key...",
                    key_position,
                    total_keys,
                )
                last_error = APIError(
                    "OddsAPI",
                    "AUTH_ERROR",
                    "The provided Odds API key was rejected.",
                )
                continue

            error_msg = sanitize_error_message(str(e))
            adaptive_timeout.record_failure()
            logger.error("Failed event odds fetch for %s: %s", sport_key, error_msg)
            raise APIError(
                "OddsAPI",
                "HTTP_ERROR",
                "Error fetching event odds.",
                error_msg,
            ) from e
        except requests.Timeout as exc:
            adaptive_timeout.record_failure()
            logger.warning("[Resilience] API timeout or network issue: %s", exc)
            logger.warning(
                "Timeout retrieving event odds for %s with key %s",
                sport_key,
                api_key,
            )
            last_error = APIError(
                "OddsAPI",
                "TIMEOUT",
                "The Odds API did not respond in time.",
            )
            continue
        except requests.ConnectionError as exc:
            adaptive_timeout.record_failure()
            sanitized_error = sanitize_error_message(str(exc))
            logger.warning("[Resilience] API timeout or network issue: %s", exc)
            logger.warning(
                "Retryable error retrieving event odds for %s with key %s: %s",
                sport_key,
                api_key,
                sanitized_error,
            )
            last_error = APIError(
                "OddsAPI",
                "NETWORK_ERROR",
                "A network error occurred.",
                sanitized_error,
            )
            continue
        except requests.RequestException as e:
            adaptive_timeout.record_failure()
            logger.warning("[Resilience] API request failure detected: %s", e)
            sanitized_error = sanitize_error_message(str(e))
            logger.warning(
                "Retryable error retrieving event odds for %s with key %s: %s",
                sport_key,
                api_key,
                sanitized_error,
            )
            last_error = APIError(
                "OddsAPI",
                "NETWORK_ERROR",
                "A network error occurred.",
                sanitized_error,
            )
            continue
        except APIError as exc:
            adaptive_timeout.record_failure()
            if exc.code not in {"TIMEOUT", "NETWORK_ERROR"}:
                raise
            sanitized_error = sanitize_error_message(exc.details or exc.message)
            logger.warning(
                "[Resilience] API timeout or network issue: %s",
                exc,
            )
            logger.warning(
                "Retryable error retrieving event odds for %s with key %s: %s",
                sport_key,
                api_key,
                sanitized_error,
            )
            message = (
                "The Odds API did not respond in time."
                if exc.code == "TIMEOUT"
                else "A network error occurred."
            )
            details = None if exc.code == "TIMEOUT" else sanitized_error
            last_error = APIError("OddsAPI", exc.code, message, details)
            continue

        try:
            return response.json()
        except ValueError as e:
            error_msg = sanitize_error_message(str(e))
            logger.error("Failed event odds fetch for %s: %s", sport_key, error_msg)
            raise APIError(
                "OddsAPI",
                "PARSE_ERROR",
                "Failed to parse API response.",
                error_msg,
            ) from e

    if last_error is not None:
        raise last_error

    raise APIError(
        "OddsAPI",
        "NETWORK_ERROR",
        "Error fetching event odds.",
    )
