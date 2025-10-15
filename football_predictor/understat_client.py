"""Client for fetching league data from the Understat API."""
from __future__ import annotations

import statistics
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from .app_utils import AdaptiveTimeoutController
from .config import API_TIMEOUT_UNDERSTAT, UNDERSTAT_CACHE_DURATION_MINUTES, setup_logger
from .errors import APIError
from .net_retry import request_with_retries
from .utils import get_current_season

# Map league codes to Understat league names
LEAGUE_MAP = {
    "PL": "epl",
    "PD": "la_liga",
    "BL1": "bundesliga",
    "SA": "serie_a",
    "FL1": "ligue_1",
    "RFPL": "rfpl",
}

# Cache for standings data (league_code_season: (data, timestamp))
_standings_cache: Dict[str, Tuple[List[Dict[str, Any]], datetime]] = {}
_cache_lock = threading.Lock()

logger = setup_logger(__name__)
adaptive_timeout = AdaptiveTimeoutController(base_timeout=API_TIMEOUT_UNDERSTAT, max_timeout=30)

_RETRY_STATUS_FORCELIST: Tuple[int, ...] = (429, 500, 502, 503, 504)
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_FACTOR = 0.6
_UNDERSTAT_API_BASE = "https://understat.com/api"


def _build_understat_url(kind: str, league: str, season: int) -> str:
    if kind == "teams":
        return f"{_UNDERSTAT_API_BASE}/teams?league={league}&season={season}"
    if kind == "fixtures":
        return f"{_UNDERSTAT_API_BASE}/fixtures?league={league}&season={season}"
    raise ValueError(f"Unknown Understat endpoint kind: {kind}")


def _extract_list(payload: Any, candidates: Iterable[str]) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in candidates:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    response = payload.get("response")
    if isinstance(response, dict):
        for key in candidates:
            value = response.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    elif isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]

    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    return []


def _request_understat_json(target_url: str, context: str) -> Dict[str, Any]:
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
        )
    except requests.Timeout as exc:
        adaptive_timeout.record_failure()
        raise APIError(
            "UnderstatAPI",
            "TIMEOUT",
            "The Understat API did not respond in time.",
        ) from exc
    except requests.RequestException as exc:
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

    try:
        resp.raise_for_status()
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

    try:
        data = resp.json()
    except ValueError as exc:
        adaptive_timeout.record_failure()
        logger.error("❌ Understat parse error: %s", exc)
        raise APIError(
            "UnderstatAPI",
            "PARSE_ERROR",
            "Failed to parse API response.",
            str(exc),
        ) from exc

    adaptive_timeout.record_success()
    return data


def _fetch_league_teams(league_code: str, understat_league: str, season: int) -> List[Dict[str, Any]]:
    target_url = _build_understat_url("teams", understat_league, season)
    payload = _request_understat_json(target_url, f"Understat teams for {league_code}")
    teams = _extract_list(payload, ("teams", "data"))
    if not teams:
        logger.warning("⚠️ Understat: No teams payload for %s", league_code)
    return teams


def _fetch_league_results(league_code: str, understat_league: str, season: int) -> List[Dict[str, Any]]:
    target_url = _build_understat_url("fixtures", understat_league, season)
    payload = _request_understat_json(target_url, f"Understat fixtures for {league_code}")
    results = _extract_list(payload, ("fixtures", "matches", "results"))
    if not results:
        logger.warning("⚠️ Understat: No fixtures payload for %s", league_code)
    return results


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
    if xg_per_game >= 1.5:
        return "Strong"
    if xg_per_game >= 1.0:
        return "Average"
    if xg_per_game >= 0.7:
        return "Weak"
    return "Poor"


def _get_defense_rating(xga_per_game: float) -> str:
    """Get defense strength rating based on xGA per game (lower is better)"""
    if xga_per_game < 0.7:
        return "Elite"
    if xga_per_game < 1.0:
        return "Strong"
    if xga_per_game < 1.5:
        return "Average"
    if xga_per_game < 2.0:
        return "Weak"
    return "Poor"


def _calculate_league_stats(teams_data: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calculate league-wide statistics for xG and xGA per game"""
    xg_per_game_values: List[float] = []
    xga_per_game_values: List[float] = []

    for team in teams_data:
        matches = team.get("match_count", team.get("played", 0))
        if matches and matches > 0:
            if team.get("xG") is not None:
                xg_per_game_values.append(float(team["xG"]) / matches)
            if team.get("xGA") is not None:
                xga_per_game_values.append(float(team["xGA"]) / matches)

    if not xg_per_game_values or not xga_per_game_values:
        return {}

    return {
        "xg_mean": round(statistics.mean(xg_per_game_values), 2),
        "xg_median": round(statistics.median(xg_per_game_values), 2),
        "xg_min": round(min(xg_per_game_values), 2),
        "xg_max": round(max(xg_per_game_values), 2),
        "xga_mean": round(statistics.mean(xga_per_game_values), 2),
        "xga_median": round(statistics.median(xga_per_game_values), 2),
        "xga_min": round(min(xga_per_game_values), 2),
        "xga_max": round(max(xga_per_game_values), 2),
    }


def _calculate_recent_trend(team_history: List[Dict[str, Any]], season_avg_xg: float) -> str:
    """Calculate if team's recent 5 games xG is above or below season average"""
    if not team_history or season_avg_xg == 0:
        return "neutral"

    recent_matches = team_history[-5:]
    if len(recent_matches) < 3:
        return "neutral"

    recent_xg = sum(float(match.get("xG", 0)) for match in recent_matches)
    recent_avg = recent_xg / len(recent_matches)

    if recent_avg > season_avg_xg * 1.1:
        return "above"
    if recent_avg < season_avg_xg * 0.9:
        return "below"
    return "neutral"


def _merge_team_metrics(
    standings: Dict[str, Dict[str, Any]],
    teams_data: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    team_xg_map: Dict[str, Dict[str, Any]] = {}
    team_history_map: Dict[str, List[Dict[str, Any]]] = {}

    for team_data in teams_data:
        team_name = team_data.get("title") or team_data.get("name")
        if not team_name:
            continue

        total_xg = 0.0
        total_xga = 0.0
        total_npxg = 0.0
        total_npxga = 0.0
        ppda_values: List[float] = []
        oppda_values: List[float] = []
        match_count = 0

        history = team_data.get("history") or team_data.get("fixtures") or []
        if isinstance(history, dict):
            history = history.get("all", [])
        if not isinstance(history, list):
            history = []
        team_history_map[team_name] = history

        for match in history:
            total_xg += float(match.get("xG", 0) or 0)
            total_xga += float(match.get("xGA", 0) or 0)
            total_npxg += float(match.get("npxG", 0) or 0)
            total_npxga += float(match.get("npxGA", 0) or 0)

            ppda = match.get("ppda", {})
            if isinstance(ppda, dict):
                att = float(ppda.get("att", 0) or 0)
                def_ = float(ppda.get("def", 0) or 0)
                if def_ > 0:
                    ppda_values.append(att / def_)

            oppda = match.get("ppda_allowed", {})
            if isinstance(oppda, dict):
                opp_att = float(oppda.get("att", 0) or 0)
                opp_def = float(oppda.get("def", 0) or 0)
                if opp_def > 0:
                    oppda_values.append(opp_att / opp_def)

            match_count += 1

        if match_count > 0:
            team_xg_map[team_name] = {
                "xG": round(total_xg, 2),
                "xGA": round(total_xga, 2),
                "npxG": round(total_npxg, 2),
                "npxGA": round(total_npxga, 2),
                "ppda_coef": round(sum(ppda_values) / len(ppda_values), 2) if ppda_values else 0,
                "oppda_coef": round(sum(oppda_values) / len(oppda_values), 2) if oppda_values else 0,
                "match_count": match_count,
            }

    standings_list: List[Dict[str, Any]] = []
    for team_name, stats in standings.items():
        stats["goal_difference"] = stats["goals_for"] - stats["goals_against"]
        stats["form"] = "".join(stats["form"][-5:])
        if team_name in team_xg_map:
            stats.update(team_xg_map[team_name])
        standings_list.append(stats)

    return standings_list, team_history_map


def _build_standings(
    league_code: str,
    teams_data: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    standings: Dict[str, Dict[str, Any]] = {}

    for match in results:
        if not isinstance(match, dict):
            continue

        if not match.get("isResult", True):
            continue

        home_team = match.get("h", {}).get("title") if isinstance(match.get("h"), dict) else match.get("home_team")
        away_team = match.get("a", {}).get("title") if isinstance(match.get("a"), dict) else match.get("away_team")

        try:
            home_goals = int(match.get("goals", {}).get("h", match.get("home_goals", 0)))
        except (TypeError, ValueError):
            home_goals = 0
        try:
            away_goals = int(match.get("goals", {}).get("a", match.get("away_goals", 0)))
        except (TypeError, ValueError):
            away_goals = 0

        for team in [home_team, away_team]:
            if team and team not in standings:
                standings[team] = {
                    "name": team,
                    "played": 0,
                    "won": 0,
                    "draw": 0,
                    "lost": 0,
                    "goals_for": 0,
                    "goals_against": 0,
                    "goal_difference": 0,
                    "points": 0,
                    "form": [],
                }

        if home_team:
            home_stats = standings[home_team]
            home_stats["played"] += 1
            home_stats["goals_for"] += home_goals
            home_stats["goals_against"] += away_goals

            if home_goals > away_goals:
                home_stats["won"] += 1
                home_stats["points"] += 3
                home_stats["form"].append("W")
            elif home_goals == away_goals:
                home_stats["draw"] += 1
                home_stats["points"] += 1
                home_stats["form"].append("D")
            else:
                home_stats["lost"] += 1
                home_stats["form"].append("L")

        if away_team:
            away_stats = standings[away_team]
            away_stats["played"] += 1
            away_stats["goals_for"] += away_goals
            away_stats["goals_against"] += home_goals

            if away_goals > home_goals:
                away_stats["won"] += 1
                away_stats["points"] += 3
                away_stats["form"].append("W")
            elif away_goals == home_goals:
                away_stats["draw"] += 1
                away_stats["points"] += 1
                away_stats["form"].append("D")
            else:
                away_stats["lost"] += 1
                away_stats["form"].append("L")

    standings_list, team_history_map = _merge_team_metrics(standings, teams_data)

    standings_list.sort(key=lambda x: (x.get("points", 0), x.get("goal_difference", 0)), reverse=True)

    for index, team in enumerate(standings_list, start=1):
        team["position"] = index

    league_stats = _calculate_league_stats(standings_list)

    xg_values = [team.get("xG", 0) for team in standings_list if team.get("xG")]
    xga_values = [team.get("xGA", 0) for team in standings_list if team.get("xGA")]
    ppda_values = [team.get("ppda_coef", 0) for team in standings_list if team.get("ppda_coef")]

    for team in standings_list:
        team_name = team["name"]
        xg = float(team.get("xG", 0) or 0)
        xga = float(team.get("xGA", 0) or 0)
        ppda = float(team.get("ppda_coef", 0) or 0)
        match_count = team.get("match_count", team.get("played", 1)) or 1

        xg_per_game = xg / match_count if match_count > 0 else 0
        xga_per_game = xga / match_count if match_count > 0 else 0

        team["xg_percentile"] = _calculate_percentile(xg, xg_values, lower_is_better=False)
        team["xga_percentile"] = _calculate_percentile(xga, xga_values, lower_is_better=True)
        team["ppda_percentile"] = _calculate_percentile(ppda, ppda_values, lower_is_better=True)

        team["attack_rating"] = _get_attack_rating(xg_per_game)
        team["defense_rating"] = _get_defense_rating(xga_per_game)

        team["league_stats"] = league_stats

        history = team_history_map.get(team_name, [])
        season_avg_xg = xg_per_game
        team["recent_trend"] = _calculate_recent_trend(history, season_avg_xg)

    logger.info("✅ Understat: Retrieved %d teams for %s", len(standings_list), league_code)
    return standings_list


def fetch_understat_standings(league_code: str, season: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch league standings from Understat with caching."""
    if season is None:
        season = get_current_season()

    cache_key = f"{league_code}_{season}"

    with _cache_lock:
        cached = _standings_cache.get(cache_key)
        if cached:
            data, timestamp = cached
            if datetime.now() - timestamp < timedelta(minutes=UNDERSTAT_CACHE_DURATION_MINUTES):
                age = datetime.now() - timestamp
                logger.info(
                    "✅ Using cached Understat data for %s (age: %ss)",
                    league_code,
                    age.seconds,
                )
                return data

    understat_league = LEAGUE_MAP.get(league_code)
    if not understat_league:
        logger.warning("⚠️ Understat: League %s not supported", league_code)
        return []

    teams_data = _fetch_league_teams(league_code, understat_league, season)
    results = _fetch_league_results(league_code, understat_league, season)

    try:
        standings = _build_standings(league_code, teams_data, results)
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

    if standings:
        with _cache_lock:
            _standings_cache[cache_key] = (standings, datetime.now())

    return standings if standings else []


def fetch_understat_match_probabilities(
    home_team: str,
    away_team: str,
    league_code: str,
    season: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch match win probabilities from Understat."""
    if season is None:
        season = get_current_season()

    understat_league = LEAGUE_MAP.get(league_code)
    if not understat_league:
        logger.warning("⚠️ Understat: League %s not supported for probabilities", league_code)
        return None

    results = _fetch_league_results(league_code, understat_league, season)

    for match in results:
        if not isinstance(match, dict):
            continue

        home = match.get("h", {}).get("title", "") if isinstance(match.get("h"), dict) else match.get("home_team", "")
        away = match.get("a", {}).get("title", "") if isinstance(match.get("a"), dict) else match.get("away_team", "")

        if (
            home_team.lower() in home.lower() or home.lower() in home_team.lower()
        ) and (
            away_team.lower() in away.lower() or away.lower() in away_team.lower()
        ):
            forecast = match.get("forecast", {})
            xg = match.get("xG", {}) if isinstance(match.get("xG"), dict) else {}
            return {
                "home_win": forecast.get("w", 0),
                "draw": forecast.get("d", 0),
                "away_win": forecast.get("l", 0),
                "home_xg": xg.get("h", match.get("home_xg", 0)),
                "away_xg": xg.get("a", match.get("away_xg", 0)),
            }

    return None
