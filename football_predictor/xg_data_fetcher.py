"""
xG Data Fetcher Module
Fetches Expected Goals (xG) statistics from FBref using soccerdata library
"""
import soccerdata as sd
import pandas as pd
from datetime import datetime, timedelta
import json
import os

# Cache settings
CACHE_DIR = "processed_data/xg_cache"
CACHE_DURATION_HOURS = 24  # Cache xG data for 24 hours

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)

# League mappings for soccerdata
LEAGUE_MAPPING = {
    "PL": "ENG-Premier League",
    "PD": "ESP-La Liga",
    "BL1": "GER-Bundesliga",
    "SA": "ITA-Serie A",
    "FL1": "FRA-Ligue 1",
    "CL": "INT-Champions League",
    "EL": "INT-Europa League"
}

# Team name normalization for FBref
TEAM_NAME_MAPPING = {
    # Premier League
    "Manchester United": "Manchester Utd",
    "Manchester City": "Manchester City",
    "Newcastle United": "Newcastle Utd",
    "Nottingham Forest": "Nott'ham Forest",
    "Brighton": "Brighton",
    "Brighton & Hove Albion": "Brighton",
    "Tottenham": "Tottenham",
    "Tottenham Hotspur": "Tottenham",
    "West Ham": "West Ham",
    "West Ham United": "West Ham",
    "Wolves": "Wolves",
    "Wolverhampton": "Wolves",
    
    # La Liga
    "Athletic Club": "Athletic Club",
    "Atletico Madrid": "Atlético Madrid",
    "Real Betis": "Betis",
    "Celta Vigo": "Celta Vigo",
    "Real Sociedad": "Sociedad",
    "Deportivo Alavés": "Alavés",
    
    # Bundesliga
    "Bayern Munich": "Bayern Munich",
    "Bayern München": "Bayern Munich",
    "Borussia Dortmund": "Dortmund",
    "Borussia Mönchengladbach": "M'Gladbach",
    "RB Leipzig": "RB Leipzig",
    "Eintracht Frankfurt": "Eintracht Frankfurt",
    
    # Serie A
    "AC Milan": "Milan",
    "Inter Milan": "Inter",
    "AS Roma": "Roma",
    
    # Ligue 1
    "Paris Saint Germain": "Paris S-G",
    "PSG": "Paris S-G",
    "Paris Saint-Germain": "Paris S-G",
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
    
    # Check if cache is older than CACHE_DURATION_HOURS
    file_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
    if datetime.now() - file_time > timedelta(hours=CACHE_DURATION_HOURS):
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
                    print(f"🔄 Migrated {team_name}: xg_overperformance → scoring_clinicality")
                
            return data
        except Exception as e:
            print(f"Error loading cache: {e}")
            return None
    
    return None


def save_to_cache(cache_key, data):
    """Save xG data to cache"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    
    try:
        with open(cache_file, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving cache: {e}")


def get_current_season():
    """Determine current season based on current date"""
    now = datetime.now()
    # Football season typically starts in August, but early season has limited data
    # Use previous season data until December to have substantial stats
    if now.month >= 12:  # December onwards, use current season
        return now.year if now.month >= 8 else now.year - 1
    elif now.month >= 8:  # August-November, use previous season (more complete data)
        return now.year - 1
    else:  # January-July, use previous season
        return now.year - 1


def fetch_fbref_league_standings(league_code, season=None):
    """
    Fetch league standings from FBref as fallback for football-data.org
    
    Args:
        league_code: League code (PL, PD, BL1, SA, FL1, CL, EL)
        season: Season year (optional)
    
    Returns:
        list: Standings data in format compatible with football-data.org
    """
    if season is None:
        season = get_current_season()
    
    # Check if league is supported
    if league_code not in LEAGUE_MAPPING:
        print(f"⚠️  League {league_code} not supported for FBref standings")
        return []
    
    league_name = LEAGUE_MAPPING[league_code]
    
    try:
        print(f"📊 Fetching FBref standings for {league_name} (season {season})...")
        fbref = sd.FBref(leagues=league_name, seasons=season)
        standings_df = fbref.read_league_table()
        
        # Convert DataFrame to list of dicts compatible with football-data.org format
        standings = []
        for idx, row in standings_df.iterrows():
            # Extract team name from MultiIndex if needed
            if isinstance(idx, tuple):
                team_name = idx[-1]  # Last element is usually the team name
            else:
                team_name = row.get('Squad', str(idx))
            
            standings.append({
                'name': team_name,
                'position': int(row.get('Rk', 0)) if pd.notna(row.get('Rk')) else 0,
                'points': int(row.get('Pts', 0)) if pd.notna(row.get('Pts')) else 0,
                'form': None  # FBref league table doesn't have form string
            })
        
        print(f"✅ Fetched FBref standings for {len(standings)} teams")
        return standings
        
    except Exception as e:
        print(f"❌ Error fetching FBref standings for {league_code}: {e}")
        return []


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
        season = get_current_season()
    
    # Check cache first
    cache_key = get_cache_key(league_code, season)
    cached_data = load_from_cache(cache_key)
    if cached_data:
        print(f"✅ Loaded xG data for {league_code} from cache")
        return cached_data
    
    # Get league name for soccerdata
    if league_code not in LEAGUE_MAPPING:
        print(f"⚠️  League {league_code} not supported for xG stats")
        return {}
    
    league_name = LEAGUE_MAPPING[league_code]
    
    try:
        # Handle season display (could be int like 2024 or string like "2024-2025")
        if isinstance(season, int):
            season_display = f"{season}-{season+1}"
        else:
            season_display = str(season)
        print(f"📊 Fetching xG stats for {league_name} (season {season_display})...")
        
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
            
            # Get goals against and xGA (PSxG) from keeper advanced stats
            goals_against = 0
            xg_against = 0
            try:
                if idx in keeper_adv_stats.index:
                    keeper_row = keeper_adv_stats.loc[idx]
                    try:
                        # Goals Against from goalkeeper stats
                        goals_against = int(keeper_row[('Goals', 'GA')])
                    except (KeyError, ValueError, TypeError):
                        pass
                    try:
                        # PSxG (Post-Shot xG) is FBref's version of xG Against
                        xg_against = float(keeper_row[('Expected', 'PSxG')])
                    except (KeyError, ValueError, TypeError):
                        pass
            except Exception:
                pass
            
            xg_data[team_name] = {
                'xg_for': xg_for,
                'xg_against': xg_against,
                'matches_played': int(matches_played) if matches_played > 0 else 1,  # Avoid division by zero
                'goals_for': goals_for,
                'goals_against': goals_against,
            }
            
            # Calculate per-game averages
            if xg_data[team_name]['matches_played'] > 0:
                matches = xg_data[team_name]['matches_played']
                xg_data[team_name]['xg_for_per_game'] = round(xg_data[team_name]['xg_for'] / matches, 2)
                xg_data[team_name]['xg_against_per_game'] = round(xg_data[team_name]['xg_against'] / matches, 2)
                xg_data[team_name]['goals_for_per_game'] = round(xg_data[team_name]['goals_for'] / matches, 2)
                xg_data[team_name]['goals_against_per_game'] = round(xg_data[team_name]['goals_against'] / matches, 2)
                
                # Calculate scoring clinicality per game (actual goals vs expected)
                # Positive = clinical finishing, Negative = wasteful
                scoring_clinicality_total = xg_data[team_name]['goals_for'] - xg_data[team_name]['xg_for']
                xg_data[team_name]['scoring_clinicality'] = round(scoring_clinicality_total / matches, 2)
            else:
                xg_data[team_name]['xg_for_per_game'] = 0
                xg_data[team_name]['xg_against_per_game'] = 0
                xg_data[team_name]['goals_for_per_game'] = 0
                xg_data[team_name]['goals_against_per_game'] = 0
                xg_data[team_name]['scoring_clinicality'] = 0
        
        
        # Save to cache
        save_to_cache(cache_key, xg_data)
        
        print(f"✅ Fetched xG stats for {len(xg_data)} teams in {league_name}")
        return xg_data
        
    except Exception as e:
        print(f"❌ Error fetching xG stats for {league_code}: {e}")
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
    
    print(f"⚠️  Team '{team_name}' not found in {league_code} xG stats")
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
    
    try:
        # Get match logs for rolling averages, form, and recent matches
        home_matches = fetch_team_match_logs(home_fbref_name, league_code, season)
        if home_matches:
            # Always compute rolling averages and form (functions handle <5 matches gracefully)
            home_rolling = calculate_rolling_averages(home_matches, 5)
            home_form = extract_last_5_results(home_matches, 5)
            # Include last 5 matches in response (convert datetime to string for JSON)
            home_recent_matches = [{
                'date': str(m['date']),
                'opponent': m['opponent'],
                'is_home': m['is_home'],
                'xg_for': m['xg_for'],
                'xg_against': m['xg_against'],
                'result': m['result']
            } for m in home_matches[:5]]
    except Exception as e:
        print(f"Could not fetch rolling data for {home_team}: {e}")
    
    try:
        away_matches = fetch_team_match_logs(away_fbref_name, league_code, season)
        if away_matches:
            # Always compute rolling averages and form (functions handle <5 matches gracefully)
            away_rolling = calculate_rolling_averages(away_matches, 5)
            away_form = extract_last_5_results(away_matches, 5)
            # Include last 5 matches in response
            away_recent_matches = [{
                'date': str(m['date']),
                'opponent': m['opponent'],
                'is_home': m['is_home'],
                'xg_for': m['xg_for'],
                'xg_against': m['xg_against'],
                'result': m['result']
            } for m in away_matches[:5]]
    except Exception as e:
        print(f"Could not fetch rolling data for {away_team}: {e}")
    
    # Calculate expected goals for the match
    # Home team expected goals = (home xGF + away xGA) / 2 * home advantage factor
    # Away team expected goals = (away xGF + home xGA) / 2
    home_advantage_factor = 1.15  # 15% home advantage
    
    home_xg = ((home_stats['xg_for_per_game'] + away_stats['xg_against_per_game']) / 2) * home_advantage_factor
    away_xg = (away_stats['xg_for_per_game'] + home_stats['xg_against_per_game']) / 2
    
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
        'home_stats': {
            'xg_for_per_game': home_stats['xg_for_per_game'],
            'xg_against_per_game': home_stats['xg_against_per_game'],
            'scoring_clinicality': home_stats['scoring_clinicality'],
            'rolling_5': home_rolling,
            'form': home_form,
            'recent_matches': home_recent_matches
        },
        'away_stats': {
            'xg_for_per_game': away_stats['xg_for_per_game'],
            'xg_against_per_game': away_stats['xg_against_per_game'],
            'scoring_clinicality': away_stats['scoring_clinicality'],
            'rolling_5': away_rolling,
            'form': away_form,
            'recent_matches': away_recent_matches
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
        print(f"⚠️  League {league_code} not supported for match logs")
        return []
    
    league_name = LEAGUE_MAPPING[league_code]
    
    # Determine season
    if not season:
        season = get_current_season()
    
    try:
        # Fetch schedule data
        print(f"📊 Fetching match logs for {team_name} in {league_name} (season {season})...")
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
            match_data = {
                'date': row['date'],
                'is_home': True,
                'opponent': row['away_team'],
                'xg_for': float(row['home_xg']) if not pd.isna(row['home_xg']) else 0,
                'xg_against': float(row['away_xg']) if not pd.isna(row['away_xg']) else 0,
                'result': parse_match_result(row['score'], True)
            }
            if match_data['result']:  # Only include completed matches
                matches.append(match_data)
        
        # Process away matches
        for idx, row in away_matches.iterrows():
            match_data = {
                'date': row['date'],
                'is_home': False,
                'opponent': row['home_team'],
                'xg_for': float(row['away_xg']) if not pd.isna(row['away_xg']) else 0,
                'xg_against': float(row['home_xg']) if not pd.isna(row['home_xg']) else 0,
                'result': parse_match_result(row['score'], False)
            }
            if match_data['result']:  # Only include completed matches
                matches.append(match_data)
        
        # Sort by date (most recent first)
        matches.sort(key=lambda x: x['date'], reverse=True)
        
        print(f"✅ Found {len(matches)} completed matches for {team_name}")
        return matches
        
    except Exception as e:
        print(f"❌ Error fetching match logs for {team_name}: {e}")
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
    print("Testing xG Data Fetcher...")
    
    # Test Premier League
    stats = fetch_league_xg_stats("PL")
    if stats:
        print(f"Found {len(stats)} teams")
        # Print first team as example
        first_team = list(stats.keys())[0]
        print(f"\nExample - {first_team}:")
        print(json.dumps(stats[first_team], indent=2))
    
    # Test match prediction
    print("\n" + "="*50)
    prediction = get_match_xg_prediction("Arsenal", "Chelsea", "PL")
    print("Match Prediction:")
    print(json.dumps(prediction, indent=2))
