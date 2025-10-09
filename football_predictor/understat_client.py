import asyncio
import aiohttp
from understat import Understat
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from functools import lru_cache
import threading

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
CACHE_DURATION = timedelta(minutes=30)  # Cache for 30 minutes

def sync_understat_call(async_func):
    """Wrapper to run async Understat functions synchronously with timeout"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(asyncio.wait_for(async_func(), timeout=10))
    except asyncio.TimeoutError:
        print("⏱️  Understat request timed out after 10 seconds")
        return [] if 'standings' in async_func.__name__ else None
    finally:
        loop.close()

async def _fetch_league_standings(league_code: str, season: int = 2024) -> List[Dict]:
    """Async function to fetch league standings from Understat"""
    understat_league = LEAGUE_MAP.get(league_code)
    
    if not understat_league:
        print(f"⚠️  League {league_code} not supported by Understat")
        return []
    
    try:
        async with aiohttp.ClientSession() as session:
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
                        'oppda_coef': round(sum(oppda_values) / len(oppda_values), 2) if oppda_values else 0
                    }
            
            # Merge xG data
            for team in standings_list:
                team_name = team['name']
                if team_name in team_xg_map:
                    team.update(team_xg_map[team_name])
            
            print(f"✅ Understat: Retrieved {len(standings_list)} teams for {league_code}")
            return standings_list
            
    except Exception as e:
        print(f"❌ Understat error for {league_code}: {str(e)}")
        return []

async def _fetch_match_probabilities(home_team: str, away_team: str, league_code: str, season: int = 2024) -> Optional[Dict]:
    """Async function to fetch match win probabilities from Understat"""
    understat_league = LEAGUE_MAP.get(league_code)
    
    if not understat_league:
        return None
    
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
    except Exception as e:
        print(f"❌ Error fetching Understat probabilities: {str(e)}")
        return None

def fetch_understat_standings(league_code: str, season: int = 2024) -> List[Dict]:
    """Sync wrapper for fetching league standings from Understat with caching"""
    cache_key = f"{league_code}_{season}"
    
    # Check cache first
    with _cache_lock:
        if cache_key in _standings_cache:
            cached_data, timestamp = _standings_cache[cache_key]
            if datetime.now() - timestamp < CACHE_DURATION:
                print(f"✅ Using cached Understat data for {league_code} (age: {(datetime.now() - timestamp).seconds}s)")
                return cached_data
    
    # Fetch fresh data
    standings = sync_understat_call(lambda: _fetch_league_standings(league_code, season))
    
    # Update cache
    if standings:
        with _cache_lock:
            _standings_cache[cache_key] = (standings, datetime.now())
    
    return standings if standings else []

def fetch_understat_match_probabilities(home_team: str, away_team: str, league_code: str, season: int = 2024) -> Optional[Dict]:
    """Sync wrapper for fetching match probabilities from Understat"""
    return sync_understat_call(lambda: _fetch_match_probabilities(home_team, away_team, league_code, season))
