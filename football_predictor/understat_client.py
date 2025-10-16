import asyncio
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import threading
import statistics
from urllib.parse import urlsplit, urlunsplit

import requests

from .app_utils import AdaptiveTimeoutController
from .config import UNDERSTAT_CACHE_DURATION_MINUTES, API_TIMEOUT_UNDERSTAT, setup_logger
from .errors import APIError
from .net_retry import request_with_retries
from .utils import get_current_season, normalize_league_code

try:  # pragma: no cover - compatibility shim for tests expecting aiohttp attribute
    import aiohttp  # type: ignore
except ImportError:  # pragma: no cover
    class _AiohttpStub:
        class ClientSession:  # type: ignore
            pass

    aiohttp = _AiohttpStub()  # type: ignore

# Map league codes to Understat league names
LEAGUE_MAP = {
    "PL": "epl",
    "PD": "la_liga",
    "BL1": "bundesliga",
    "SA": "serie_a",
    "FL1": "ligue_1",
    "RFPL": "rfpl"
}

# Cache for standings data (league_code_season: (data, timestamp))
_standings_cache = {}
_cache_lock = threading.Lock()

logger = setup_logger(__name__)
adaptive_timeout = AdaptiveTimeoutController(base_timeout=API_TIMEOUT_UNDERSTAT, max_timeout=30)

_RETRY_STATUS_FORCELIST = (429, 500, 502, 503, 504)
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_FACTOR = 0.6

_UNDERSTAT_API_BASE = "https://understat.com/api"


def _scrub_url(url: Any) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(str(url))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    except Exception:
        return str(url)


def _make_understat_request(
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    context: str,
) -> Dict[str, Any] | List[Any]:
    target_url = f"{_UNDERSTAT_API_BASE}{path}"

    try:
        resp = request_with_retries(
            method="GET",
            url=target_url,
            timeout=adaptive_timeout.get_timeout(),
            retries=_RETRY_ATTEMPTS,
            backoff_factor=_RETRY_BACKOFF_FACTOR,
            status_forcelist=_RETRY_STATUS_FORCELIST,
            logger=logger,
            context=context,
            params=params,
        )
        resp.raise_for_status()
        adaptive_timeout.record_success()
    except requests.Timeout as exc:
        adaptive_timeout.record_failure()
        raise APIError(
            "UnderstatAPI",
            "TIMEOUT",
            "The Understat API did not respond in time.",
        ) from exc
    except requests.HTTPError as exc:
        adaptive_timeout.record_failure()
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 429:
            raise APIError(
                "UnderstatAPI",
                "429",
                "The Understat API rate limited the request.",
                "rate_limited",
            ) from exc
        raise APIError(
            "UnderstatAPI",
            "NETWORK_ERROR",
            "A network error occurred.",
            str(exc),
        ) from exc
    except requests.RequestException as exc:
        adaptive_timeout.record_failure()
        raise APIError(
            "UnderstatAPI",
            "NETWORK_ERROR",
            "A network error occurred.",
            str(exc),
        ) from exc

    try:
        return resp.json()
    except ValueError as exc:
        adaptive_timeout.record_failure()
        raise APIError(
            "UnderstatAPI",
            "PARSE_ERROR",
            "Failed to parse API response.",
            str(exc),
        ) from exc

def _calculate_percentile(value: float, all_values: List[float], lower_is_better: bool = False) -> float:
    """Calculate percentile rank for a value (0-100, where 100 is best)"""
    if not all_values or value is None:
        return 0.0
    
    sorted_values = sorted(all_values, reverse=not lower_is_better)
    try:
        rank = sorted_values.index(value) + 1
    except ValueError:
        rank = len(sorted_values)
    
    percentile = (rank / len(all_values)) * 100
    return round(percentile, 1)

def _get_attack_rating(xg_per_game: float) -> str:
    """Get attack strength rating based on xG per game"""
    if xg_per_game >= 2.0:
        return "Elite"
    elif xg_per_game >= 1.5:
        return "Strong"
    elif xg_per_game >= 1.0:
        return "Average"
    elif xg_per_game >= 0.7:
        return "Weak"
    else:
        return "Poor"

def _get_defense_rating(xga_per_game: float) -> str:
    """Get defense strength rating based on xGA per game (lower is better)"""
    if xga_per_game < 0.7:
        return "Elite"
    elif xga_per_game < 1.0:
        return "Strong"
    elif xga_per_game < 1.5:
        return "Average"
    elif xga_per_game < 2.0:
        return "Weak"
    else:
        return "Poor"

def _calculate_league_stats(teams_data: List[Dict]) -> Dict:
    """Calculate league-wide statistics for xG and xGA per game"""
    # Calculate per-game values for each team
    xg_per_game_values = []
    xga_per_game_values = []
    
    for team in teams_data:
        matches = team.get('match_count', team.get('played', 0))
        if matches > 0:
            if team.get('xG') is not None:
                xg_per_game_values.append(team['xG'] / matches)
            if team.get('xGA') is not None:
                xga_per_game_values.append(team['xGA'] / matches)
    
    if not xg_per_game_values or not xga_per_game_values:
        return {}
    
    return {
        'xg_mean': round(statistics.mean(xg_per_game_values), 2),
        'xg_median': round(statistics.median(xg_per_game_values), 2),
        'xg_min': round(min(xg_per_game_values), 2),
        'xg_max': round(max(xg_per_game_values), 2),
        'xga_mean': round(statistics.mean(xga_per_game_values), 2),
        'xga_median': round(statistics.median(xga_per_game_values), 2),
        'xga_min': round(min(xga_per_game_values), 2),
        'xga_max': round(max(xga_per_game_values), 2)
    }

def _calculate_recent_trend(team_history: List[Dict], season_avg_xg: float) -> str:
    """Calculate if team's recent 5 games xG is above or below season average"""
    if not team_history or season_avg_xg == 0:
        return "neutral"
    
    recent_matches = team_history[-5:]
    if len(recent_matches) < 3:
        return "neutral"
    
    recent_xg = sum(float(match.get('xG', 0)) for match in recent_matches)
    recent_avg = recent_xg / len(recent_matches)
    
    if recent_avg > season_avg_xg * 1.1:
        return "above"
    elif recent_avg < season_avg_xg * 0.9:
        return "below"
    else:
        return "neutral"

def _extract_dict_list(payload: Any, *, candidate_keys: Tuple[str, ...]) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in candidate_keys:
            if key in payload:
                extracted = _extract_dict_list(payload[key], candidate_keys=candidate_keys)
                if extracted:
                    return extracted
        if payload and all(isinstance(value, dict) for value in payload.values()):
            return [value for value in payload.values() if isinstance(value, dict)]
    return []


def _fetch_league_standings(league_code: str, season: Optional[int] = None) -> List[Dict]:
    """Fetch league standings from Understat using the retry-enabled HTTP helper."""
    if season is None:
        season = get_current_season()

    normalized_code = normalize_league_code(league_code)
    canonical_code = normalized_code or (str(league_code).strip().upper() if league_code else "")

    understat_league = LEAGUE_MAP.get(canonical_code)

    if not understat_league:
        logger.warning("⚠️ Understat: League %s not supported", league_code)
        return []

    context_prefix = f"standings:{canonical_code or league_code}:{season}"

    try:
        teams_payload = _make_understat_request(
            "/league/table",
            params={"league": understat_league, "season": season},
            context=f"{context_prefix}:teams",
        )
        results_payload = _make_understat_request(
            "/league/results",
            params={"league": understat_league, "season": season},
            context=f"{context_prefix}:results",
        )
    except APIError:
        raise
    except Exception as exc:
        logger.exception("❌ Unexpected Understat error for %s", league_code)
        raise APIError(
            "UnderstatAPI",
            "UNKNOWN_ERROR",
            "An unexpected error occurred while contacting Understat.",
            str(exc),
        ) from exc

    teams = _extract_dict_list(
        teams_payload,
        candidate_keys=(
            "teams",
            "teamsData",
            "data",
            "result",
            "table",
            "response",
            "all",
        ),
    )
    results = _extract_dict_list(
        results_payload,
        candidate_keys=(
            "results",
            "fixtures",
            "matches",
            "response",
            "list",
            "data",
        ),
    )

    standings: Dict[str, Dict[str, Any]] = {}
    for match in results:
        if not match.get('isResult', True):
            continue

        home_info = match.get('h') or match.get('home') or {}
        away_info = match.get('a') or match.get('away') or {}

        home_team = home_info.get('title') or home_info.get('team_name') or home_info.get('name')
        away_team = away_info.get('title') or away_info.get('team_name') or away_info.get('name')

        goals = match.get('goals') or match.get('score') or {}
        home_goals = int(goals.get('h') or goals.get('home') or home_info.get('goals', 0) or 0)
        away_goals = int(goals.get('a') or goals.get('away') or away_info.get('goals', 0) or 0)

        for team in [home_team, away_team]:
            if team and team not in standings:
                standings[team] = {
                    'name': team,
                    'played': 0,
                    'won': 0,
                    'draw': 0,
                    'lost': 0,
                    'goals_for': 0,
                    'goals_against': 0,
                    'goal_difference': 0,
                    'points': 0,
                    'form': [],
                }

        if home_team:
            team_entry = standings[home_team]
            team_entry['played'] += 1
            team_entry['goals_for'] += home_goals
            team_entry['goals_against'] += away_goals
            if home_goals > away_goals:
                team_entry['won'] += 1
                team_entry['points'] += 3
                team_entry['form'].append('W')
            elif home_goals == away_goals:
                team_entry['draw'] += 1
                team_entry['points'] += 1
                team_entry['form'].append('D')
            else:
                team_entry['lost'] += 1
                team_entry['form'].append('L')

        if away_team:
            team_entry = standings[away_team]
            team_entry['played'] += 1
            team_entry['goals_for'] += away_goals
            team_entry['goals_against'] += home_goals
            if away_goals > home_goals:
                team_entry['won'] += 1
                team_entry['points'] += 3
                team_entry['form'].append('W')
            elif away_goals == home_goals:
                team_entry['draw'] += 1
                team_entry['points'] += 1
                team_entry['form'].append('D')
            else:
                team_entry['lost'] += 1
                team_entry['form'].append('L')

    standings_list: List[Dict[str, Any]] = []
    for team_name, stats in standings.items():
        stats['goal_difference'] = stats['goals_for'] - stats['goals_against']
        stats['form'] = ''.join(stats['form'][-5:])
        standings_list.append(stats)

    standings_list.sort(key=lambda x: (x['points'], x['goal_difference']), reverse=True)

    for idx, team in enumerate(standings_list, 1):
        team['position'] = idx

    team_xg_map: Dict[str, Dict[str, Any]] = {}
    team_history_map: Dict[str, List[Dict[str, Any]]] = {}

    for team_data in teams:
        team_name = (
            team_data.get('title')
            or team_data.get('team_title')
            or team_data.get('team_name')
            or team_data.get('name')
        )
        if not team_name:
            continue

        history = team_data.get('history')
        if isinstance(history, dict):
            history = list(history.values())
        if not isinstance(history, list):
            history = []
        team_history_map[team_name] = history

        total_xg = 0.0
        total_xga = 0.0
        total_npxg = 0.0
        total_npxga = 0.0
        ppda_values: List[float] = []
        oppda_values: List[float] = []
        match_count = 0

        for match in history:
            total_xg += float(match.get('xG', 0))
            total_xga += float(match.get('xGA', 0))
            total_npxg += float(match.get('npxG', 0))
            total_npxga += float(match.get('npxGA', 0))

            ppda = match.get('ppda', {})
            if isinstance(ppda, dict):
                att = float(ppda.get('att', 0))
                def_ = float(ppda.get('def', 0))
                if def_ > 0:
                    ppda_values.append(att / def_)

            oppda = match.get('ppda_allowed', {})
            if isinstance(oppda, dict):
                opp_att = float(oppda.get('att', 0))
                opp_def = float(oppda.get('def', 0))
                if opp_def > 0:
                    oppda_values.append(opp_att / opp_def)

            match_count += 1

        if match_count > 0:
            team_xg_map[team_name] = {
                'xG': round(total_xg, 2),
                'xGA': round(total_xga, 2),
                'npxG': round(total_npxg, 2),
                'npxGA': round(total_npxga, 2),
                'ppda_coef': round(sum(ppda_values) / len(ppda_values), 2) if ppda_values else 0,
                'oppda_coef': round(sum(oppda_values) / len(oppda_values), 2) if oppda_values else 0,
                'match_count': match_count,
            }

    for team in standings_list:
        team_name = team['name']
        if team_name in team_xg_map:
            team.update(team_xg_map[team_name])

    league_stats = _calculate_league_stats(standings_list)

    xg_values = [team.get('xG', 0) for team in standings_list if team.get('xG')]
    xga_values = [team.get('xGA', 0) for team in standings_list if team.get('xGA')]
    ppda_values = [team.get('ppda_coef', 0) for team in standings_list if team.get('ppda_coef')]

    for team in standings_list:
        team_name = team['name']
        xg = team.get('xG', 0)
        xga = team.get('xGA', 0)
        ppda = team.get('ppda_coef', 0)
        match_count = team.get('match_count', team.get('played', 1))

        xg_per_game = xg / match_count if match_count > 0 else 0
        xga_per_game = xga / match_count if match_count > 0 else 0

        team['xg_percentile'] = _calculate_percentile(xg, xg_values, lower_is_better=False)
        team['xga_percentile'] = _calculate_percentile(xga, xga_values, lower_is_better=True)
        team['ppda_percentile'] = _calculate_percentile(ppda, ppda_values, lower_is_better=True)

        team['attack_rating'] = _get_attack_rating(xg_per_game)
        team['defense_rating'] = _get_defense_rating(xga_per_game)

        team['league_stats'] = league_stats

        history = team_history_map.get(team_name, [])
        season_avg_xg = xg_per_game
        team['recent_trend'] = _calculate_recent_trend(history, season_avg_xg)

    logger.info(
        "✅ Understat: Retrieved %d teams for %s",
        len(standings_list),
        canonical_code or league_code,
    )
    return standings_list

def _fetch_match_probabilities(
    home_team: str,
    away_team: str,
    league_code: str,
    season: Optional[int] = None,
) -> Optional[Dict]:
    """Fetch match win probabilities from Understat using retry-enabled HTTP requests."""
    if season is None:
        season = get_current_season()

    normalized_code = normalize_league_code(league_code)
    canonical_code = normalized_code or (str(league_code).strip().upper() if league_code else "")

    understat_league = LEAGUE_MAP.get(canonical_code)

    if not understat_league:
        logger.warning("⚠️ Understat: League %s not supported for probabilities", league_code)
        return None

    try:
        results_payload = _make_understat_request(
            "/league/results",
            params={"league": understat_league, "season": season},
            context=f"probabilities:{canonical_code or league_code}:{season}",
        )
    except APIError:
        raise
    except Exception as exc:
        logger.exception("❌ Unexpected Understat error fetching probabilities")
        raise APIError(
            "UnderstatAPI",
            "UNKNOWN_ERROR",
            "An unexpected error occurred while contacting Understat.",
            str(exc),
        ) from exc

    results = _extract_dict_list(
        results_payload,
        candidate_keys=(
            "results",
            "fixtures",
            "matches",
            "response",
            "list",
            "data",
        ),
    )

    home_normalized = home_team.lower()
    away_normalized = away_team.lower()

    for match in results:
        home_info = match.get('h') or match.get('home') or {}
        away_info = match.get('a') or match.get('away') or {}

        home_title = (home_info.get('title') or home_info.get('team_name') or home_info.get('name') or "").lower()
        away_title = (away_info.get('title') or away_info.get('team_name') or away_info.get('name') or "").lower()

        if (home_normalized in home_title or home_title in home_normalized) and (
            away_normalized in away_title or away_title in away_normalized
        ):
            forecast = match.get('forecast', {})
            xg_values = match.get('xG') or match.get('xg') or {}
            return {
                'home_win': forecast.get('w', 0),
                'draw': forecast.get('d', 0),
                'away_win': forecast.get('l', 0),
                'home_xg': xg_values.get('h') or xg_values.get('home', 0),
                'away_xg': xg_values.get('a') or xg_values.get('away', 0),
            }

    return None

def fetch_understat_standings(league_code: str, season: Optional[int] = None) -> List[Dict]:
    """Sync wrapper for fetching league standings from Understat with caching"""
    if season is None:
        season = get_current_season()
    
    normalized_code = normalize_league_code(league_code)
    canonical_code = normalized_code or (str(league_code).strip().upper() if league_code else "")
    cache_key = f"{canonical_code}_{season}"
    
    # Check cache first
    with _cache_lock:
        if cache_key in _standings_cache:
            cached_data, timestamp = _standings_cache[cache_key]
            if datetime.now() - timestamp < timedelta(minutes=UNDERSTAT_CACHE_DURATION_MINUTES):
                age = datetime.now() - timestamp
                logger.info(
                    "✅ Using cached Understat data for %s (age: %ss)",
                    canonical_code or league_code,
                    age.seconds,
                )
                return cached_data

    # Fetch fresh data
    standings = _fetch_league_standings(canonical_code or league_code, season)
    
    # Update cache
    if standings:
        with _cache_lock:
            _standings_cache[cache_key] = (standings, datetime.now())
    
    return standings if standings else []

def fetch_understat_match_probabilities(home_team: str, away_team: str, league_code: str, season: Optional[int] = None) -> Optional[Dict]:
    """Sync wrapper for fetching match probabilities from Understat"""
    if season is None:
        season = get_current_season()
    
    return _fetch_match_probabilities(home_team, away_team, league_code, season)
