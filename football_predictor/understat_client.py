import asyncio
import statistics
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    import aiohttp
except ModuleNotFoundError:  # pragma: no cover - optional dependency in tests
    aiohttp = None
    _AIOHTTP_AVAILABLE = False
    class _AiohttpStub:
        ClientError = RuntimeError

    aiohttp = _AiohttpStub()  # type: ignore[assignment]
else:
    _AIOHTTP_AVAILABLE = True

try:
    from understat import Understat
except ModuleNotFoundError:  # pragma: no cover - optional dependency in tests
    Understat = None

from .app_utils import AdaptiveTimeoutController
from .utils import get_current_season
from .config import UNDERSTAT_CACHE_DURATION_MINUTES, API_TIMEOUT_UNDERSTAT, setup_logger
from .errors import APIError

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


def _require_understat() -> None:
    """Ensure the optional Understat dependency is available."""

    if Understat is None:
        raise APIError(
            "UnderstatAPI",
            "MISSING_DEPENDENCY",
            "The optional 'understat' package is not installed.",
        )


def _require_aiohttp() -> None:
    """Ensure the optional aiohttp dependency is available."""

    if not _AIOHTTP_AVAILABLE:
        raise APIError(
            "UnderstatAPI",
            "MISSING_DEPENDENCY",
            "The optional 'aiohttp' package is not installed.",
        )

def sync_understat_call(async_func, context: str = "Understat API call"):
    """Wrapper to run async Understat functions synchronously with timeout"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    timeout = adaptive_timeout.get_timeout()

    try:
        result = loop.run_until_complete(
            asyncio.wait_for(async_func(), timeout=timeout)
        )
        adaptive_timeout.record_success()
        return result
    except asyncio.TimeoutError as exc:
        adaptive_timeout.record_failure()
        logger.warning("[Resilience] API timeout or network issue: %s", exc)
        logger.error(
            "⏱️ Understat request timed out after %.1f seconds (%s)",
            timeout,
            context,
        )
        raise APIError(
            "UnderstatAPI",
            "TIMEOUT",
            "The Understat API did not respond in time.",
        ) from exc
    except APIError:
        raise
    except aiohttp.ClientError as exc:
        adaptive_timeout.record_failure()
        logger.warning("[Resilience] API request failure detected: %s", exc)
        logger.error("❌ Understat error during %s: %s", context, exc)
        raise APIError(
            "UnderstatAPI",
            "NETWORK_ERROR",
            "A network error occurred.",
            str(exc),
        ) from exc
    except Exception as exc:
        adaptive_timeout.record_failure()
        logger.warning("[Resilience] API request failure detected: %s", exc)
        logger.error("❌ Understat error during %s: %s", context, exc)
        raise APIError(
            "UnderstatAPI",
            "NETWORK_ERROR",
            "A network error occurred.",
            str(exc),
        ) from exc
    finally:
        loop.close()

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

async def _fetch_league_standings(league_code: str, season: Optional[int] = None) -> List[Dict]:
    """Async function to fetch league standings from Understat"""
    if season is None:
        season = get_current_season()

    understat_league = LEAGUE_MAP.get(league_code)

    if not understat_league:
        logger.warning("⚠️ Understat: League %s not supported", league_code)
        return []

    _require_understat()
    _require_aiohttp()

    timeout = adaptive_timeout.get_timeout()
    session_kwargs: Dict[str, Any] = {}

    if hasattr(aiohttp, "ClientTimeout"):
        try:
            session_kwargs["timeout"] = aiohttp.ClientTimeout(total=timeout)
        except Exception:
            session_kwargs = {}

    try:
        async with aiohttp.ClientSession(**session_kwargs) as session:
            understat = Understat(session)

            # Get team stats
            teams = await understat.get_teams(understat_league, season)

            # Get league results to extract standings
            results = await understat.get_league_results(understat_league, season)

            # Build standings table
            standings = {}
            for match in results:
                if not match.get('isResult'):
                    continue
                
                home_team = match.get('h', {}).get('title')
                away_team = match.get('a', {}).get('title')
                home_goals = int(match.get('goals', {}).get('h', 0))
                away_goals = int(match.get('goals', {}).get('a', 0))
                
                # Initialize team stats
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
                            'form': []
                        }
                
                # Update home team
                if home_team:
                    standings[home_team]['played'] += 1
                    standings[home_team]['goals_for'] += home_goals
                    standings[home_team]['goals_against'] += away_goals
                    
                    if home_goals > away_goals:
                        standings[home_team]['won'] += 1
                        standings[home_team]['points'] += 3
                        standings[home_team]['form'].append('W')
                    elif home_goals == away_goals:
                        standings[home_team]['draw'] += 1
                        standings[home_team]['points'] += 1
                        standings[home_team]['form'].append('D')
                    else:
                        standings[home_team]['lost'] += 1
                        standings[home_team]['form'].append('L')
                
                # Update away team
                if away_team:
                    standings[away_team]['played'] += 1
                    standings[away_team]['goals_for'] += away_goals
                    standings[away_team]['goals_against'] += home_goals
                    
                    if away_goals > home_goals:
                        standings[away_team]['won'] += 1
                        standings[away_team]['points'] += 3
                        standings[away_team]['form'].append('W')
                    elif away_goals == home_goals:
                        standings[away_team]['draw'] += 1
                        standings[away_team]['points'] += 1
                        standings[away_team]['form'].append('D')
                    else:
                        standings[away_team]['lost'] += 1
                        standings[away_team]['form'].append('L')
            
            # Calculate goal difference and convert to list
            standings_list = []
            for team_name, stats in standings.items():
                stats['goal_difference'] = stats['goals_for'] - stats['goals_against']
                # Keep only last 5 form results
                stats['form'] = ''.join(stats['form'][-5:])
                standings_list.append(stats)
            
            # Sort by points, then goal difference
            standings_list.sort(key=lambda x: (x['points'], x['goal_difference']), reverse=True)
            
            # Add position
            for i, team in enumerate(standings_list, 1):
                team['position'] = i
            
            # Merge with xG data from teams endpoint (aggregated from matches)
            team_xg_map = {}
            team_history_map = {}
            
            for team_data in teams:
                team_name = team_data.get('title')
                if not team_name:
                    continue
                
                # Aggregate xG data from all matches
                total_xg = 0
                total_xga = 0
                total_npxg = 0
                total_npxga = 0
                ppda_values = []
                oppda_values = []
                match_count = 0
                
                history = team_data.get('history', [])
                team_history_map[team_name] = history
                
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
                        'match_count': match_count
                    }
            
            # Merge xG data
            for team in standings_list:
                team_name = team['name']
                if team_name in team_xg_map:
                    team.update(team_xg_map[team_name])
            
            # Calculate league-wide statistics
            league_stats = _calculate_league_stats(standings_list)
            
            # Collect values for percentile calculations
            xg_values = [team.get('xG', 0) for team in standings_list if team.get('xG')]
            xga_values = [team.get('xGA', 0) for team in standings_list if team.get('xGA')]
            ppda_values = [team.get('ppda_coef', 0) for team in standings_list if team.get('ppda_coef')]
            
            # Add enhanced metrics to each team
            for team in standings_list:
                team_name = team['name']
                xg = team.get('xG', 0)
                xga = team.get('xGA', 0)
                ppda = team.get('ppda_coef', 0)
                match_count = team.get('match_count', team.get('played', 1))
                
                # Calculate per-game averages
                xg_per_game = xg / match_count if match_count > 0 else 0
                xga_per_game = xga / match_count if match_count > 0 else 0
                
                # Calculate percentiles (lower is better for xGA and PPDA)
                team['xg_percentile'] = _calculate_percentile(xg, xg_values, lower_is_better=False)
                team['xga_percentile'] = _calculate_percentile(xga, xga_values, lower_is_better=True)
                team['ppda_percentile'] = _calculate_percentile(ppda, ppda_values, lower_is_better=True)
                
                # Calculate performance ratings
                team['attack_rating'] = _get_attack_rating(xg_per_game)
                team['defense_rating'] = _get_defense_rating(xga_per_game)
                
                # Add league context
                team['league_stats'] = league_stats
                
                # Calculate recent trend
                history = team_history_map.get(team_name, [])
                season_avg_xg = xg_per_game
                team['recent_trend'] = _calculate_recent_trend(history, season_avg_xg)
            
            logger.info(
                "✅ Understat: Retrieved %d teams for %s",
                len(standings_list),
                league_code,
            )
            return standings_list

    except aiohttp.ClientError as exc:
        error_msg = str(exc)
        logger.error("❌ Understat network error for %s: %s", league_code, error_msg)
        raise APIError(
            "UnderstatAPI",
            "NETWORK_ERROR",
            "A network error occurred.",
            error_msg,
        ) from exc
    except ValueError as exc:
        error_msg = str(exc)
        logger.error("❌ Understat parse error for %s: %s", league_code, error_msg)
        raise APIError(
            "UnderstatAPI",
            "PARSE_ERROR",
            "Failed to parse API response.",
            error_msg,
        ) from exc
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

async def _fetch_match_probabilities(home_team: str, away_team: str, league_code: str, season: Optional[int] = None) -> Optional[Dict]:
    """Async function to fetch match win probabilities from Understat"""
    if season is None:
        season = get_current_season()
    
    understat_league = LEAGUE_MAP.get(league_code)

    if not understat_league:
        logger.warning("⚠️ Understat: League %s not supported for probabilities", league_code)
        return None

    _require_understat()
    _require_aiohttp()

    try:
        async with aiohttp.ClientSession() as session:
            understat = Understat(session)
            results = await understat.get_league_results(understat_league, season)

            # Find the specific match
            for match in results:
                home = match.get('h', {}).get('title', '')
                away = match.get('a', {}).get('title', '')

                # Fuzzy match team names
                if (home_team.lower() in home.lower() or home.lower() in home_team.lower()) and \
                   (away_team.lower() in away.lower() or away.lower() in away_team.lower()):

                    forecast = match.get('forecast', {})
                    return {
                        'home_win': forecast.get('w', 0),
                        'draw': forecast.get('d', 0),
                        'away_win': forecast.get('l', 0),
                        'home_xg': match.get('xG', {}).get('h', 0),
                        'away_xg': match.get('xG', {}).get('a', 0)
                    }

            return None
    except aiohttp.ClientError as exc:
        error_msg = str(exc)
        logger.error("❌ Understat network error fetching probabilities: %s", error_msg)
        raise APIError(
            "UnderstatAPI",
            "NETWORK_ERROR",
            "A network error occurred.",
            error_msg,
        ) from exc
    except ValueError as exc:
        error_msg = str(exc)
        logger.error("❌ Understat parse error fetching probabilities: %s", error_msg)
        raise APIError(
            "UnderstatAPI",
            "PARSE_ERROR",
            "Failed to parse API response.",
            error_msg,
        ) from exc
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

def fetch_understat_standings(league_code: str, season: Optional[int] = None) -> List[Dict]:
    """Sync wrapper for fetching league standings from Understat with caching"""
    if season is None:
        season = get_current_season()
    
    cache_key = f"{league_code}_{season}"
    
    # Check cache first
    with _cache_lock:
        if cache_key in _standings_cache:
            cached_data, timestamp = _standings_cache[cache_key]
            if datetime.now() - timestamp < timedelta(minutes=UNDERSTAT_CACHE_DURATION_MINUTES):
                age = datetime.now() - timestamp
                logger.info(
                    "✅ Using cached Understat data for %s (age: %ss)",
                    league_code,
                    age.seconds,
                )
                return cached_data

    # Fetch fresh data
    standings = sync_understat_call(
        lambda: _fetch_league_standings(league_code, season),
        context=f"Understat standings for {league_code}",
    )
    
    # Update cache
    if standings:
        with _cache_lock:
            _standings_cache[cache_key] = (standings, datetime.now())
    
    return standings if standings else []

def fetch_understat_match_probabilities(home_team: str, away_team: str, league_code: str, season: Optional[int] = None) -> Optional[Dict]:
    """Sync wrapper for fetching match probabilities from Understat"""
    if season is None:
        season = get_current_season()
    
    return sync_understat_call(
        lambda: _fetch_match_probabilities(home_team, away_team, league_code, season),
        context=f"Understat probabilities for {home_team} vs {away_team}",
    )
