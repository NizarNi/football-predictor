"""
xG Data Fetcher Module
Fetches Expected Goals (xG) statistics from FBref using soccerdata library
"""
import soccerdata as sd
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import get_xg_season
from config import setup_logger, XG_CACHE_DURATION_HOURS, TEAM_NAME_MAP_FBREF as TEAM_NAME_MAPPING

# Cache settings
CACHE_DIR = "processed_data/xg_cache"

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)

# In-memory cache for match logs (team+league+season -> {data, timestamp})
MATCH_LOGS_CACHE = {}
MATCH_LOGS_CACHE_TTL = 300  # 5 minutes in seconds

# Career xG cache (team+league -> {data, timestamp})
CAREER_XG_CACHE = {}
CAREER_XG_CACHE_TTL = 604800  # 7 days in seconds for historical data

logger = setup_logger(__name__)

# League mappings for soccerdata
# League code mapping (Our codes → FBref league names)
# Note: FBref only supports the Big 5 European leagues
# Champions League and Europa League are NOT supported by FBref
LEAGUE_MAPPING = {
    "PL": "ENG-Premier League",
    "PD": "ESP-La Liga",
    "BL1": "GER-Bundesliga",
    "SA": "ITA-Serie A",
    "FL1": "FRA-Ligue 1",
    # "CL": Not supported by FBref
    # "EL": Not supported by FBref
}


def normalize_team_name_for_fbref(team_name):
    """Normalize team names to match FBref's naming conventions"""
    # Check if we have a direct mapping
    if team_name in TEAM_NAME_MAPPING:
        return TEAM_NAME_MAPPING[team_name]
    
    # Return original if no mapping found
    return team_name


def get_cache_key(league_code, season):
    """Generate cache key for xG data"""
    return f"{league_code}_{season}"


def is_cache_valid(cache_file):
    """Check if cache file exists and is still valid"""
    if not os.path.exists(cache_file):
        return False
    
    # Check if cache is older than XG_CACHE_DURATION_HOURS
    file_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
    if datetime.now() - file_time > timedelta(hours=XG_CACHE_DURATION_HOURS):
        return False
    
    return True


def load_from_cache(cache_key):
    """Load xG data from cache with backward compatibility"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    
    if is_cache_valid(cache_file):
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                
            # Backward compatibility: migrate old xg_overperformance to scoring_clinicality
            for team_name, team_data in data.items():
                if 'xg_overperformance' in team_data and 'scoring_clinicality' not in team_data:
                    team_data['scoring_clinicality'] = team_data['xg_overperformance']
                    logger.info("🔄 Migrated %s: xg_overperformance → scoring_clinicality", team_name)

            return data
        except Exception as e:
            logger.exception("Error loading cache")
            return None
    
    return None


def save_to_cache(cache_key, data):
    """Save xG data to cache"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    
    try:
        with open(cache_file, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.exception("Error saving cache")


def fetch_career_xg_stats(team_name, league_code):
    """
    Fetch recent historical xG statistics for a team (last 5 seasons)
    
    Args:
        team_name: Team name to fetch career stats for
        league_code: League code (e.g., 'PL', 'PD')
    
    Returns:
        dict: Career xG statistics with averages across recent seasons
    """
    # Check if league is supported
    if league_code not in LEAGUE_MAPPING:
        logger.warning("⚠️  League %s not supported for career xG", league_code)
        return None
    
    # Check cache first
    cache_key = f"{team_name}_{league_code}_career"
    current_time = datetime.now().timestamp()
    
    if cache_key in CAREER_XG_CACHE:
        cached_data = CAREER_XG_CACHE[cache_key]
        cache_age = current_time - cached_data['timestamp']
        if cache_age < CAREER_XG_CACHE_TTL:
            logger.info(
                "✅ Using cached career xG for %s (age: %.1f days)",
                team_name,
                cache_age / 86400,
            )
            return cached_data['data']
    
    league_name = LEAGUE_MAPPING[league_code]
    normalized_name = normalize_team_name_for_fbref(team_name)
    
    # Collect xG data across seasons
    seasons_data = []
    current_season = get_xg_season()
    
    # Fetch last 5 seasons only to avoid rate limiting (reduced from 2010)
    start_season = max(2021, current_season - 4)
    
    logger.info(
        "📊 Fetching career xG for %s in %s (%d-%d)...",
        team_name,
        league_name,
        start_season,
        current_season,
    )
    
    # Try seasons from start to current
    for season in range(start_season, current_season + 1):
        try:
            fbref = sd.FBref(leagues=league_name, seasons=season)
            stats_df = fbref.read_team_season_stats(stat_type='standard')
            
            # Find team in stats
            team_stats = None
            for idx, row in stats_df.iterrows():
                # Extract team name from MultiIndex
                if isinstance(idx, tuple):
                    team_in_row = idx[-1]
                else:
                    team_in_row = str(idx)
                
                if team_in_row == normalized_name or team_in_row == team_name:
                    team_stats = row
                    break
            
            if team_stats is not None:
                # Extract xG metrics - FBref uses multi-index columns
                # Try different column name variations for xG
                xg_for = 0
                xga = 0
                games = 0
                
                # Expected xG columns
                if ('Expected', 'xG') in team_stats.index:
                    xg_for = float(team_stats[('Expected', 'xG')]) if pd.notna(team_stats[('Expected', 'xG')]) else 0
                elif 'xG' in team_stats.index:
                    xg_for = float(team_stats['xG']) if pd.notna(team_stats['xG']) else 0
                
                # Expected xGA columns
                if ('Expected', 'xGA') in team_stats.index:
                    xga = float(team_stats[('Expected', 'xGA')]) if pd.notna(team_stats[('Expected', 'xGA')]) else 0
                elif 'xGA' in team_stats.index:
                    xga = float(team_stats['xGA']) if pd.notna(team_stats['xGA']) else 0
                
                # Matches Played columns
                if ('Standard', 'MP') in team_stats.index:
                    games = int(team_stats[('Standard', 'MP')]) if pd.notna(team_stats[('Standard', 'MP')]) else 0
                elif ('Playing Time', 'MP') in team_stats.index:
                    games = int(team_stats[('Playing Time', 'MP')]) if pd.notna(team_stats[('Playing Time', 'MP')]) else 0
                elif 'MP' in team_stats.index:
                    games = int(team_stats['MP']) if pd.notna(team_stats['MP']) else 0
                
                if games > 0:
                    seasons_data.append({
                        'season': f"{season}/{str(season+1)[-2:]}",
                        'season_year': season,
                        'xg_for': xg_for,
                        'xga': xga,
                        'games': games,
                        'xg_for_per_game': round(xg_for / games, 2),
                        'xga_per_game': round(xga / games, 2)
                    })
                    
        except Exception as e:
            # Team might not have been in this league this season
            continue
        
        # Add delay to avoid FBref rate limiting (429 errors)
        if season < current_season:
            time.sleep(2)
    
    if not seasons_data:
        logger.warning("⚠️  No historical xG data found for %s", team_name)
        return None
    
    # Calculate career averages
    total_xg = sum(s['xg_for'] for s in seasons_data)
    total_xga = sum(s['xga'] for s in seasons_data)
    total_games = sum(s['games'] for s in seasons_data)
    seasons_count = len(seasons_data)
    
    career_stats = {
        'team': team_name,
        'league': league_code,
        'seasons_count': seasons_count,
        'total_games': total_games,
        'career_xg_per_game': round(total_xg / total_games, 2) if total_games > 0 else 0,
        'career_xga_per_game': round(total_xga / total_games, 2) if total_games > 0 else 0,
        'first_season': seasons_data[0]['season'],
        'last_season': seasons_data[-1]['season'],
        'seasons_data': seasons_data  # Include individual season data
    }
    
    logger.info(
        "✅ Career xG for %s: %s xG/game over %d seasons (%d games)",
        team_name,
        career_stats['career_xg_per_game'],
        seasons_count,
        total_games,
    )
    
    # Cache the results
    CAREER_XG_CACHE[cache_key] = {
        'data': career_stats,
        'timestamp': datetime.now().timestamp()
    }
    
    return career_stats


def fetch_league_xg_stats(league_code, season=None):
    """
    Fetch xG statistics for all teams in a league
    
    Args:
        league_code: League code (PL, PD, BL1, SA, FL1, CL, EL)
        season: Season year (e.g., 2024 for 2024-25 season). If None, uses current season.
    
    Returns:
        dict: Team xG statistics {team_name: {xg_for, xg_against, matches_played, ...}}
    """
    if season is None:
        season = get_xg_season()
    
    # Check cache first
    cache_key = get_cache_key(league_code, season)
    cached_data = load_from_cache(cache_key)
    if cached_data:
        logger.info("✅ Loaded xG data for %s from cache", league_code)
        return cached_data

    # Get league name for soccerdata
    if league_code not in LEAGUE_MAPPING:
        logger.warning("⚠️  League %s not supported for xG stats", league_code)
        return {}
    
    league_name = LEAGUE_MAPPING[league_code]
    
    try:
        # Handle season display (could be int like 2024 or string like "2024-2025")
        if isinstance(season, int):
            season_display = f"{season}-{season+1}"
        else:
            season_display = str(season)
        logger.info("📊 Fetching xG stats for %s (season %s)...", league_name, season_display)
        
        # Fetch team stats from FBref
        fbref = sd.FBref(leagues=league_name, seasons=season)
        
        # Get team offensive and defensive stats
        shooting_stats = fbref.read_team_season_stats(stat_type='shooting')  # xG For
        standard_stats = fbref.read_team_season_stats(stat_type='standard')  # Matches played
        keeper_adv_stats = fbref.read_team_season_stats(stat_type='keeper_adv')  # Goals Against, PSxG (xGA)
        
        # Process stats into a usable format
        xg_data = {}
        
        for idx, row in shooting_stats.iterrows():
            # Index is MultiIndex: (league, season, team) - extract team name from position 2
            team_name = idx[2] if isinstance(idx, tuple) and len(idx) >= 3 else str(idx)
            
            # FBref uses MultiIndex columns - access as tuples
            # Shooting stats columns: ('Standard', 'Gls'), ('Expected', 'xG'), etc.
            try:
                xg_for = float(row[('Expected', 'xG')])
            except (KeyError, ValueError, TypeError):
                xg_for = 0
            
            try:
                goals_for = int(row[('Standard', 'Gls')])
            except (KeyError, ValueError, TypeError):
                goals_for = 0
            
            # Get matches played from standard stats
            matches_played = 0
            try:
                if idx in standard_stats.index:
                    std_row = standard_stats.loc[idx]
                    try:
                        # Use 'MP' (Matches Played) from Playing Time columns
                        matches_played = int(std_row[('Playing Time', 'MP')])
                    except (KeyError, ValueError, TypeError):
                        # Fallback to 90s if MP not available
                        try:
                            matches_played = int(std_row[('Playing Time', '90s')])
                        except:
                            matches_played = 0
            except Exception:
                pass
            
            # Get goals against and PSxG (Post-Shot xG Against) from keeper advanced stats
            goals_against = 0
            ps_xg_against = 0  # Post-Shot xG Against (goalkeeper quality)
            try:
                if idx in keeper_adv_stats.index:
                    keeper_row = keeper_adv_stats.loc[idx]
                    try:
                        # Goals Against from goalkeeper stats
                        goals_against = int(keeper_row[('Goals', 'GA')])
                    except (KeyError, ValueError, TypeError):
                        pass
                    try:
                        # PSxG (Post-Shot xG Against) - measures goalkeeper shot-stopping quality
                        # Only counts on-target shots, considers shot placement/power/trajectory
                        ps_xg_against = float(keeper_row[('Expected', 'PSxG')])
                    except (KeyError, ValueError, TypeError):
                        pass
            except Exception:
                pass
            
            # NOTE: FBref only provides PSxG (Post-Shot xG Against), NOT true xGA
            # True defensive xGA comes from Understat (via /context endpoint)
            # We store PSxGA in both xg_against (legacy) and ps_xg_against (explicit) fields
            xg_data[team_name] = {
                'xg_for': xg_for,
                'xg_against': ps_xg_against,  # PSxGA (goalkeeper quality) - legacy field name for backwards compatibility
                'ps_xg_against': ps_xg_against,  # PSxGA (goalkeeper quality) - explicit field name
                'matches_played': int(matches_played) if matches_played > 0 else 1,  # Avoid division by zero
                'goals_for': goals_for,
                'goals_against': goals_against,
            }
            
            # Calculate per-game averages
            if xg_data[team_name]['matches_played'] > 0:
                matches = xg_data[team_name]['matches_played']
                xg_data[team_name]['xg_for_per_game'] = round(xg_data[team_name]['xg_for'] / matches, 2)
                # Note: xg_against_per_game is PSxGA (goalkeeper quality), NOT defensive xGA
                # Defensive xGA comes from Understat via /context endpoint
                xg_data[team_name]['xg_against_per_game'] = round(xg_data[team_name]['xg_against'] / matches, 2)  
                xg_data[team_name]['ps_xg_against_per_game'] = round(xg_data[team_name]['ps_xg_against'] / matches, 2)
                xg_data[team_name]['goals_for_per_game'] = round(xg_data[team_name]['goals_for'] / matches, 2)
                xg_data[team_name]['goals_against_per_game'] = round(xg_data[team_name]['goals_against'] / matches, 2)
                
                # Calculate scoring clinicality per game (actual goals vs expected)
                # Positive = clinical finishing, Negative = wasteful
                scoring_clinicality_total = xg_data[team_name]['goals_for'] - xg_data[team_name]['xg_for']
                xg_data[team_name]['scoring_clinicality'] = round(scoring_clinicality_total / matches, 2)
                
                # Calculate goalkeeper performance (PSxG+/- per game)
                # Positive = saves more than expected, Negative = concedes more than expected  
                ps_xg_performance = xg_data[team_name]['ps_xg_against'] - xg_data[team_name]['goals_against']
                xg_data[team_name]['ps_xg_performance'] = round(ps_xg_performance / matches, 2)
            else:
                xg_data[team_name]['xg_for_per_game'] = 0
                xg_data[team_name]['xg_against_per_game'] = 0
                xg_data[team_name]['ps_xg_against_per_game'] = 0
                xg_data[team_name]['goals_for_per_game'] = 0
                xg_data[team_name]['goals_against_per_game'] = 0
                xg_data[team_name]['scoring_clinicality'] = 0
                xg_data[team_name]['ps_xg_performance'] = 0
        
        
        # Save to cache
        save_to_cache(cache_key, xg_data)
        
        logger.info("✅ Fetched xG stats for %d teams in %s", len(xg_data), league_name)
        return xg_data

    except Exception as e:
        logger.exception("❌ Error fetching xG stats for %s", league_code)
        return {}


def get_team_xg_stats(team_name, league_code, season=None):
    """
    Get xG statistics for a specific team
    
    Args:
        team_name: Team name
        league_code: League code
        season: Season year (optional)
    
    Returns:
        dict: Team xG statistics or None if not found
    """
    # Fetch league stats (will use cache if available)
    league_stats = fetch_league_xg_stats(league_code, season)
    
    if not league_stats:
        return None
    
    # Normalize team name for FBref
    normalized_name = normalize_team_name_for_fbref(team_name)
    
    # Try to find team with exact match
    if normalized_name in league_stats:
        return league_stats[normalized_name]
    
    # Try original name
    if team_name in league_stats:
        return league_stats[team_name]
    
    # Try fuzzy matching (case-insensitive partial match)
    team_name_lower = team_name.lower()
    for fbref_team, stats in league_stats.items():
        if team_name_lower in fbref_team.lower() or fbref_team.lower() in team_name_lower:
            return stats
    
    logger.warning("⚠️  Team '%s' not found in %s xG stats", team_name, league_code)
    return None


def get_match_xg_prediction(home_team, away_team, league_code, season=None):
    """
    Generate xG-based prediction for a match
    
    Args:
        home_team: Home team name
        away_team: Away team name
        league_code: League code
        season: Season year (optional)
    
    Returns:
        dict: Match xG prediction with expected goals, over/under likelihood, rolling averages, and form
    """
    home_stats = get_team_xg_stats(home_team, league_code, season)
    away_stats = get_team_xg_stats(away_team, league_code, season)
    
    if not home_stats or not away_stats:
        # Provide specific messaging for unsupported leagues
        if league_code in ['CL', 'EL']:
            league_name = 'Champions League' if league_code == 'CL' else 'Europa League'
            return {
                'available': False,
                'error': f'xG data not available for {league_name} (FBref only supports domestic leagues: Premier League, La Liga, Bundesliga, Serie A, Ligue 1)'
            }
        return {
            'available': False,
            'error': 'xG data not available for one or both teams'
        }
    
    # Get FBref team names for match logs
    home_fbref_name = normalize_team_name_for_fbref(home_team)
    away_fbref_name = normalize_team_name_for_fbref(away_team)
    
    # Fetch rolling averages, form, and recent matches (if available)
    home_rolling = {'xg_for_rolling': None, 'xg_against_rolling': None, 'matches_count': 0}
    away_rolling = {'xg_for_rolling': None, 'xg_against_rolling': None, 'matches_count': 0}
    home_form = None
    away_form = None
    home_recent_matches = []
    away_recent_matches = []
    
    # Fetch home and away match logs in parallel for performance
    home_matches = []
    away_matches = []
    
    logger.info("🔄 Fetching match logs in parallel for both teams...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Submit both fetch tasks
        future_home = executor.submit(fetch_team_match_logs, home_fbref_name, league_code, season)
        future_away = executor.submit(fetch_team_match_logs, away_fbref_name, league_code, season)
        
        # Get results
        try:
            home_matches = future_home.result(timeout=30)
        except Exception as e:
            logger.warning("Could not fetch rolling data for %s: %s", home_team, e)

        try:
            away_matches = future_away.result(timeout=30)
        except Exception as e:
            logger.warning("Could not fetch rolling data for %s: %s", away_team, e)
    
    # Process home team data
    if home_matches:
        home_rolling = calculate_rolling_averages(home_matches, 5)
        home_form = extract_last_5_results(home_matches, 5)
        home_recent_matches = [{
            'date': str(m['date']),
            'opponent': m['opponent'],
            'is_home': m['is_home'],
            'xg_for': m['xg_for'],
            'xg_against': m['xg_against'],
            'result': m['result']
        } for m in home_matches[:5]]
    
    # Process away team data
    if away_matches:
        away_rolling = calculate_rolling_averages(away_matches, 5)
        away_form = extract_last_5_results(away_matches, 5)
        away_recent_matches = [{
            'date': str(m['date']),
            'opponent': m['opponent'],
            'is_home': m['is_home'],
            'xg_for': m['xg_for'],
            'xg_against': m['xg_against'],
            'result': m['result']
        } for m in away_matches[:5]]
    
    # Calculate expected goals for the match
    # Use rolling 5-game averages if available (better recent form indicator)
    # Fallback to season averages if insufficient data
    home_advantage_factor = 1.15  # 15% home advantage
    
    # Determine which xG values to use (rolling vs season averages)
    # Prefer rolling if we have at least 3 matches
    use_home_rolling = home_rolling['matches_count'] >= 3 and home_rolling['xg_for_rolling'] is not None
    use_away_rolling = away_rolling['matches_count'] >= 3 and away_rolling['xg_for_rolling'] is not None
    
    home_xgf = home_rolling['xg_for_rolling'] if use_home_rolling else home_stats['xg_for_per_game']
    home_xga = home_rolling['xg_against_rolling'] if use_home_rolling else home_stats['xg_against_per_game']
    away_xgf = away_rolling['xg_for_rolling'] if use_away_rolling else away_stats['xg_for_per_game']
    away_xga = away_rolling['xg_against_rolling'] if use_away_rolling else away_stats['xg_against_per_game']
    
    # Home team expected goals = (home xGF + away xGA) / 2 * home advantage factor
    # Away team expected goals = (away xGF + home xGA) / 2
    home_xg = ((home_xgf + away_xga) / 2) * home_advantage_factor
    away_xg = (away_xgf + home_xga) / 2
    
    total_xg = home_xg + away_xg
    
    # Over/Under 2.5 prediction
    # Using a simple probability model based on Poisson distribution approximation
    over_2_5_probability = min(95, max(5, int((total_xg - 2.5) * 30 + 50)))
    
    # Result prediction based on xG
    if home_xg - away_xg > 0.5:
        result_prediction = "HOME_WIN"
        confidence = min(80, int(40 + (home_xg - away_xg) * 20))
    elif away_xg - home_xg > 0.5:
        result_prediction = "AWAY_WIN"
        confidence = min(80, int(40 + (away_xg - home_xg) * 20))
    else:
        result_prediction = "DRAW"
        confidence = min(60, int(30 + abs(home_xg - away_xg) * 10))
    
    return {
        'available': True,
        'home_team': home_team,
        'away_team': away_team,
        'home_xg': round(home_xg, 2),
        'away_xg': round(away_xg, 2),
        'total_xg': round(total_xg, 2),
        'data_source_home': 'rolling_5' if use_home_rolling else 'season_avg',
        'data_source_away': 'rolling_5' if use_away_rolling else 'season_avg',
        'home_stats': {
            'xg_for_per_game': home_stats['xg_for_per_game'],
            'xg_against_per_game': home_stats['xg_against_per_game'],
            'scoring_clinicality': home_stats['scoring_clinicality'],
            'rolling_5': home_rolling,
            'form': home_form,
            'recent_matches': home_recent_matches,
            'using_rolling': use_home_rolling
        },
        'away_stats': {
            'xg_for_per_game': away_stats['xg_for_per_game'],
            'xg_against_per_game': away_stats['xg_against_per_game'],
            'scoring_clinicality': away_stats['scoring_clinicality'],
            'rolling_5': away_rolling,
            'form': away_form,
            'recent_matches': away_recent_matches,
            'using_rolling': use_away_rolling
        },
        'over_under_2_5': {
            'prediction': 'OVER' if over_2_5_probability > 50 else 'UNDER',
            'over_probability': over_2_5_probability,
            'under_probability': 100 - over_2_5_probability
        },
        'result_prediction': {
            'prediction': result_prediction,
            'confidence': confidence
        }
    }


def parse_match_result(score, is_home_team):
    """
    Parse match score to determine result (W/D/L)
    
    Args:
        score: Score string (e.g., "2-1", "1-1")
        is_home_team: Boolean indicating if team is playing at home
    
    Returns:
        str: 'W', 'D', or 'L'
    """
    if not score or pd.isna(score) or score == '':
        return None
    
    try:
        # Handle both hyphen (-) and en-dash (–) in scores
        score_str = str(score).replace('–', '-')
        parts = score_str.split('-')
        if len(parts) != 2:
            return None
            
        home_goals = int(parts[0])
        away_goals = int(parts[1])
        
        if is_home_team:
            if home_goals > away_goals:
                return 'W'
            elif home_goals == away_goals:
                return 'D'
            else:
                return 'L'
        else:
            if away_goals > home_goals:
                return 'W'
            elif home_goals == away_goals:
                return 'D'
            else:
                return 'L'
    except:
        return None


def safe_extract_value(row, column_name, default=None):
    """
    Safely extract a value from a pandas row, handling Series/scalar issues
    
    Args:
        row: pandas row object
        column_name: Column name to extract
        default: Default value if extraction fails
    
    Returns:
        Extracted scalar value or default
    """
    try:
        value = row[column_name]
        # If it's a Series, extract the first value
        if isinstance(value, pd.Series):
            return value.iloc[0] if len(value) > 0 else default
        return value if pd.notna(value) else default
    except (KeyError, IndexError, AttributeError):
        return default


def fetch_team_match_logs(team_name, league_code, season=None):
    """
    Fetch match-by-match logs for a team including xG and results
    
    Args:
        team_name: Team name to fetch logs for
        league_code: League code (e.g., 'PL', 'PD')
        season: Season year (optional)
    
    Returns:
        list: List of match dictionaries with xG, results, and form
    """
    # Check if league is supported
    if league_code not in LEAGUE_MAPPING:
        logger.warning("⚠️  League %s not supported for match logs", league_code)
        return []
    
    league_name = LEAGUE_MAPPING[league_code]
    
    # Determine season
    if not season:
        season = get_xg_season()
    
    # Check cache first
    cache_key = f"{team_name}_{league_code}_{season}"
    current_time = datetime.now().timestamp()
    
    if cache_key in MATCH_LOGS_CACHE:
        cached_data = MATCH_LOGS_CACHE[cache_key]
        cache_age = current_time - cached_data['timestamp']
        if cache_age < MATCH_LOGS_CACHE_TTL:
            logger.info("✅ Using cached match logs for %s (age: %.1fs)", team_name, cache_age)
            return cached_data['data']
    
    try:
        # Fetch schedule data
        logger.info("📊 Fetching match logs for %s in %s (season %s)...", team_name, league_name, season)
        fbref = sd.FBref(league_name, season)
        schedule = fbref.read_schedule()
        
        # Normalize team name for matching
        normalized_name = normalize_team_name_for_fbref(team_name)
        
        # Get home and away matches
        home_matches = schedule[schedule['home_team'] == normalized_name].copy()
        away_matches = schedule[schedule['away_team'] == normalized_name].copy()
        
        # If no matches found with normalized name, try original name
        if len(home_matches) == 0 and len(away_matches) == 0:
            home_matches = schedule[schedule['home_team'] == team_name].copy()
            away_matches = schedule[schedule['away_team'] == team_name].copy()
        
        # Process matches
        matches = []
        
        # Process home matches
        for idx, row in home_matches.iterrows():
            # Extract xG values safely (handle both scalar and Series)
            try:
                home_xg = row['home_xg']
                # Convert Series to scalar if needed
                if isinstance(home_xg, pd.Series):
                    home_xg = home_xg.iloc[0] if len(home_xg) > 0 else None
                home_xg_value = float(home_xg) if (home_xg is not None and pd.notna(home_xg)) else 0
            except (ValueError, TypeError, AttributeError):
                home_xg_value = 0
            
            try:
                away_xg = row['away_xg']
                # Convert Series to scalar if needed
                if isinstance(away_xg, pd.Series):
                    away_xg = away_xg.iloc[0] if len(away_xg) > 0 else None
                away_xg_value = float(away_xg) if (away_xg is not None and pd.notna(away_xg)) else 0
            except (ValueError, TypeError, AttributeError):
                away_xg_value = 0
            
            # Extract gameweek if available  
            gameweek = None
            try:
                gw_value = row.get('gameweek', None)
                if gw_value is not None and pd.notna(gw_value):
                    gameweek = int(gw_value)
            except (ValueError, TypeError, AttributeError):
                pass
            
            match_data = {
                'date': safe_extract_value(row, 'date'),
                'is_home': True,
                'opponent': safe_extract_value(row, 'away_team', 'Unknown'),
                'gameweek': gameweek,
                'xg_for': home_xg_value,
                'xg_against': away_xg_value,
                'result': parse_match_result(safe_extract_value(row, 'score'), True)
            }
            if match_data['result']:  # Only include completed matches
                matches.append(match_data)
        
        # Process away matches
        for idx, row in away_matches.iterrows():
            # Extract xG values safely (handle both scalar and Series)
            try:
                away_xg = row['away_xg']
                # Convert Series to scalar if needed
                if isinstance(away_xg, pd.Series):
                    away_xg = away_xg.iloc[0] if len(away_xg) > 0 else None
                away_xg_value = float(away_xg) if (away_xg is not None and pd.notna(away_xg)) else 0
            except (ValueError, TypeError, AttributeError):
                away_xg_value = 0
            
            try:
                home_xg = row['home_xg']
                # Convert Series to scalar if needed
                if isinstance(home_xg, pd.Series):
                    home_xg = home_xg.iloc[0] if len(home_xg) > 0 else None
                home_xg_value = float(home_xg) if (home_xg is not None and pd.notna(home_xg)) else 0
            except (ValueError, TypeError, AttributeError):
                home_xg_value = 0
            
            # Extract gameweek if available  
            gameweek = None
            try:
                gw_value = row.get('gameweek', None)
                if gw_value is not None and pd.notna(gw_value):
                    gameweek = int(gw_value)
            except (ValueError, TypeError, AttributeError):
                pass
            
            match_data = {
                'date': safe_extract_value(row, 'date'),
                'is_home': False,
                'opponent': safe_extract_value(row, 'home_team', 'Unknown'),
                'gameweek': gameweek,
                'xg_for': away_xg_value,
                'xg_against': home_xg_value,
                'result': parse_match_result(safe_extract_value(row, 'score'), False)
            }
            if match_data['result']:  # Only include completed matches
                matches.append(match_data)
        
        # Sort by date (most recent first)
        matches.sort(key=lambda x: x['date'], reverse=True)
        
        logger.info("✅ Found %d completed matches for %s", len(matches), team_name)
        
        # Cache the results
        MATCH_LOGS_CACHE[cache_key] = {
            'data': matches,
            'timestamp': datetime.now().timestamp()
        }
        
        return matches
        
    except Exception as e:
        logger.exception("❌ Error fetching match logs for %s", team_name)
        return []


def calculate_rolling_averages(matches, window=5):
    """
    Calculate rolling averages for xG metrics
    
    Args:
        matches: List of match dictionaries (sorted by date, most recent first)
        window: Number of matches for rolling average (default 5)
    
    Returns:
        dict: Rolling averages for xGF and xGA
    """
    if len(matches) < window:
        window = len(matches)
    
    if window == 0:
        return {
            'xg_for_rolling': 0,
            'xg_against_rolling': 0,
            'matches_count': 0
        }
    
    # Get last N matches
    recent_matches = matches[:window]
    
    # Calculate averages
    xg_for_total = sum(m['xg_for'] for m in recent_matches)
    xg_against_total = sum(m['xg_against'] for m in recent_matches)
    
    return {
        'xg_for_rolling': round(xg_for_total / window, 2),
        'xg_against_rolling': round(xg_against_total / window, 2),
        'matches_count': window
    }


def extract_last_5_results(matches, limit=5):
    """
    Extract last N match results as form string
    
    Args:
        matches: List of match dictionaries (sorted by date, most recent first)
        limit: Number of results to extract (default 5)
    
    Returns:
        str: Form string (e.g., 'WLDWW')
    """
    if len(matches) < limit:
        limit = len(matches)
    
    form = ''.join([m['result'] for m in matches[:limit] if m['result']])
    return form


# Test function
if __name__ == "__main__":
    # Test fetching xG stats
    logger.info("Testing xG Data Fetcher...")

    # Test Premier League
    stats = fetch_league_xg_stats("PL")
    if stats:
        logger.info("Found %d teams", len(stats))
        # Print first team as example
        first_team = list(stats.keys())[0]
        logger.info("Example - %s:", first_team)
        logger.info(json.dumps(stats[first_team], indent=2))

    # Test match prediction
    logger.info("=" * 50)
    prediction = get_match_xg_prediction("Arsenal", "Chelsea", "PL")
    logger.info("Match Prediction:")
    logger.info(json.dumps(prediction, indent=2))
