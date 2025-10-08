"""
xG Data Fetcher Module
Fetches Expected Goals (xG) statistics from FBref using soccerdata library
"""
import soccerdata as sd
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
    """Load xG data from cache"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    
    if is_cache_valid(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
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
        print(f"📊 Fetching xG stats for {league_name} (season {season}-{season+1})...")
        
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
                
                # Calculate xG overperformance (actual goals vs expected)
                xg_data[team_name]['xg_overperformance'] = round(
                    xg_data[team_name]['goals_for'] - xg_data[team_name]['xg_for'], 2
                )
            else:
                xg_data[team_name]['xg_for_per_game'] = 0
                xg_data[team_name]['xg_against_per_game'] = 0
                xg_data[team_name]['goals_for_per_game'] = 0
                xg_data[team_name]['goals_against_per_game'] = 0
                xg_data[team_name]['xg_overperformance'] = 0
        
        
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
        dict: Match xG prediction with expected goals and over/under likelihood
    """
    home_stats = get_team_xg_stats(home_team, league_code, season)
    away_stats = get_team_xg_stats(away_team, league_code, season)
    
    if not home_stats or not away_stats:
        return {
            'available': False,
            'error': 'xG data not available for one or both teams'
        }
    
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
            'xg_overperformance': home_stats['xg_overperformance']
        },
        'away_stats': {
            'xg_for_per_game': away_stats['xg_for_per_game'],
            'xg_against_per_game': away_stats['xg_against_per_game'],
            'xg_overperformance': away_stats['xg_overperformance']
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
