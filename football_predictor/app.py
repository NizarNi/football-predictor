from flask import Flask, render_template, request, jsonify
import os
import json
from datetime import datetime
import sys

# Import our custom modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from football_data_api import get_competitions, get_upcoming_matches, get_match_details, RateLimitExceededError
from odds_api_client import get_upcoming_matches_with_odds, OddsAPIError, LEAGUE_CODE_MAPPING
from odds_calculator import calculate_predictions_from_odds
from xg_data_fetcher import get_match_xg_prediction

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Create directories if they don't exist
os.makedirs("scraped_data", exist_ok=True)
os.makedirs("processed_data", exist_ok=True)
os.makedirs("models", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Global variables
# Supported league codes for football-data.org API
SUPPORTED_LEAGUES = ["PL", "PD", "BL1", "SA", "FL1", "CL", "EL"]



@app.route("/")
def index():
    """Render the home page"""
    return render_template("index.html")

@app.route("/demo")
def demo():
    """Demo page to showcase Over/Under and Match Context features (static version)"""
    try:
        with open('/tmp/demo_static.html', 'r') as f:
            return f.read()
    except:
        return "Demo page not available", 404

@app.route("/upcoming", methods=["GET"])
def upcoming():
    """Get upcoming matches with predictions using The Odds API (primary) and football-data.org (fallback)"""
    league_code = request.args.get("league", None)
    next_n_days = request.args.get("next_n_days", 30, type=int)
    
    try:
        # Try The Odds API first (provides both matches and odds-based predictions)
        print(f"🔍 Fetching matches with odds from The Odds API...")
        try:
            if league_code:
                if league_code not in LEAGUE_CODE_MAPPING:
                    return jsonify({"error": f"League code \"{league_code}\" not supported"}), 404
                leagues_to_fetch = [league_code]
            else:
                leagues_to_fetch = list(LEAGUE_CODE_MAPPING.keys())
            
            odds_matches = get_upcoming_matches_with_odds(league_codes=leagues_to_fetch, next_n_days=next_n_days)
            
            if odds_matches:
                # Calculate predictions from odds for each match
                for match in odds_matches:
                    predictions = calculate_predictions_from_odds(match)
                    
                    # Format match data
                    match["datetime"] = match["commence_time"]
                    match["timestamp"] = datetime.fromisoformat(match["commence_time"].replace('Z', '+00:00')).timestamp()
                    
                    # Add predictions in the expected format
                    match["predictions"] = {
                        "1x2": {
                            "prediction": predictions["prediction"],
                            "confidence": predictions["confidence"],
                            "probabilities": predictions["probabilities"],
                            "is_safe_bet": predictions["confidence"] >= 60,
                            "bookmaker_count": predictions["bookmaker_count"]
                        },
                        "best_odds": predictions["best_odds"],
                        "arbitrage": predictions["arbitrage"]
                    }
                
                print(f"✅ Found {len(odds_matches)} matches from The Odds API")
                return jsonify({
                    "matches": odds_matches,
                    "total_matches": len(odds_matches),
                    "source": "The Odds API"
                })
        except OddsAPIError as e:
            print(f"⚠️  The Odds API unavailable: {e}")
        except Exception as e:
            print(f"⚠️  The Odds API error: {e}")
        
        # Fallback to football-data.org (no predictions)
        print(f"🔄 Falling back to football-data.org...")
        
        if league_code:
            if league_code not in SUPPORTED_LEAGUES:
                return jsonify({"error": f"League code \"{league_code}\" not supported"}), 404
            leagues_to_fetch = [league_code]
        else:
            leagues_to_fetch = SUPPORTED_LEAGUES

        all_upcoming_matches = []
        for league in leagues_to_fetch:
            try:
                matches = get_upcoming_matches(league, next_n_days=next_n_days)
                if matches:
                    all_upcoming_matches.extend(matches)
                    print(f"Found {len(matches)} matches for {league}")
            except RateLimitExceededError as api_e:
                print(f"Rate limit exceeded for {league}: {api_e}")
                continue
            except Exception as api_e:
                print(f"Error fetching matches for {league}: {api_e}")
        
        if not all_upcoming_matches:
            return jsonify({"error": "No upcoming matches found"}), 404
        
        # Sort and format matches
        upcoming_matches = sorted(all_upcoming_matches, key=lambda x: x["timestamp"])
        
        for match in upcoming_matches:
            match["datetime"] = datetime.fromtimestamp(match["timestamp"]).strftime("%Y-%m-%d %H:%M")
            match["predictions"] = {
                "note": "Predictions unavailable - using fallback data source"
            }

        return jsonify({
            "matches": upcoming_matches,
            "total_matches": len(upcoming_matches),
            "source": "football-data.org (fallback)"
        })
        
    except Exception as e:
        print(f"❌ Critical error: {e}")
        return jsonify({"error": str(e)}), 500





@app.route("/search", methods=["POST"])
def search():
    """Search for matches by team name"""
    team_name = request.form.get("team_name", "").strip()
    
    if not team_name:
        return jsonify({"error": "Please provide a team name"}), 400
    
    try:
        print(f"🔍 Searching for team: {team_name}")
        
        # Use The Odds API to fetch matches from all leagues
        try:
            odds_matches = get_upcoming_matches_with_odds(
                league_codes=list(LEAGUE_CODE_MAPPING.keys()), 
                next_n_days=30
            )
            
            if not odds_matches:
                # No matches from Odds API - return empty result
                print(f"ℹ️ No matches available from The Odds API")
                return jsonify({"error": f"No matches found for team '{team_name}' - try again later"}), 404
            
            # Filter matches by team name
            team_name_lower = team_name.lower()
            filtered_matches = [
                match for match in odds_matches
                if team_name_lower in match.get("home_team", "").lower() or 
                   team_name_lower in match.get("away_team", "").lower()
            ]
            
            if not filtered_matches:
                return jsonify({"error": f"No matches found for team '{team_name}'"}), 404
            
            # Calculate predictions from odds for each match
            for match in filtered_matches:
                predictions = calculate_predictions_from_odds(match)
                
                # Format match data
                match["datetime"] = match["commence_time"]
                match["timestamp"] = datetime.fromisoformat(match["commence_time"].replace('Z', '+00:00')).timestamp()
                
                # Add predictions in the expected format
                match["predictions"] = {
                    "1x2": {
                        "prediction": predictions["prediction"],
                        "confidence": predictions["confidence"],
                        "probabilities": predictions["probabilities"],
                        "is_safe_bet": predictions["confidence"] >= 60,
                        "bookmaker_count": predictions["bookmaker_count"]
                    },
                    "best_odds": predictions["best_odds"],
                    "arbitrage": predictions["arbitrage"]
                }
            
            # Sort by date
            filtered_matches = sorted(filtered_matches, key=lambda x: x["timestamp"])
            
            print(f"✅ Found {len(filtered_matches)} matches for '{team_name}' from The Odds API")
            return jsonify({
                "matches": filtered_matches,
                "source": "The Odds API"
            })
                
        except Exception as odds_e:
            print(f"⚠️ The Odds API error during search: {odds_e}")
            return jsonify({"error": "Search service temporarily unavailable"}), 503
        
    except Exception as e:
        print(f"Error in search: {e}")
        return jsonify({"error": f"Search failed: {str(e)}"}), 500

@app.route("/match/<match_id>", methods=["GET"])
def get_match(match_id):
    """Get detailed information about a specific match"""
    try:
        # Try to get match details from football-data.org
        match_details = get_match_details(match_id)
        
        if not match_details:
            return jsonify({"error": f"Match with ID {match_id} not found"}), 404
        
        # Format the response to match frontend expectations
        response = {
            "match": {
                "id": match_details.get("id"),
                "home": {
                    "name": match_details.get("home_team", {}).get("name", "Unknown")
                },
                "away": {
                    "name": match_details.get("away_team", {}).get("name", "Unknown")
                },
                "stage": match_details.get("league", "Unknown"),
                "date": match_details.get("date"),
                "timestamp": match_details.get("timestamp"),
                "datetime": datetime.fromtimestamp(match_details.get("timestamp", 0)).strftime("%Y-%m-%d %H:%M") if match_details.get("timestamp") else "TBD",
                "status": match_details.get("status", "SCHEDULED"),
                "venue": match_details.get("venue", "Unknown")
            }
        }
        
        # Add score if available
        if "score" in match_details:
            response["match"]["score"] = match_details["score"]
        
        return jsonify(response)
        
    except RateLimitExceededError as e:
        return jsonify({"error": f"Rate limit exceeded: {str(e)}"}), 429
    except Exception as e:
        print(f"Error fetching match {match_id}: {e}")
        return jsonify({"error": f"Failed to fetch match details: {str(e)}"}), 500

@app.route("/predict/<match_id>", methods=["GET"])
def predict_match(match_id):
    """Get predictions for a specific match"""
    try:
        response = {
            "predictions": {
                "1x2": {
                    "prediction": "N/A",
                    "confidence": 0,
                    "probabilities": {
                        "HOME_WIN": 0.33,
                        "DRAW": 0.33,
                        "AWAY_WIN": 0.33
                    },
                    "is_safe_bet": False,
                    "note": "Individual match predictions available when browsing upcoming matches with odds"
                },
                "best_odds": None,
                "arbitrage": None
            },
            "note": "Prediction data with odds is available when browsing upcoming matches"
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error predicting match {match_id}: {e}")
        return jsonify({"error": f"Failed to get predictions: {str(e)}"}), 500

@app.route("/match/<event_id>/totals", methods=["GET"])
def get_match_totals(event_id):
    """Get over/under predictions for a specific match on-demand"""
    try:
        sport_key = request.args.get("sport_key")
        if not sport_key:
            return jsonify({"error": "sport_key parameter required"}), 400
        
        from odds_api_client import get_event_odds
        from odds_calculator import calculate_totals_from_odds
        
        odds_data = get_event_odds(sport_key, event_id, regions="us,uk,eu", markets="totals")
        
        if not odds_data:
            return jsonify({"error": "No totals odds found for this match"}), 404
        
        totals_predictions = calculate_totals_from_odds(odds_data)
        
        return jsonify({
            "totals": totals_predictions,
            "source": "The Odds API"
        })
        
    except Exception as e:
        print(f"Error fetching totals for {event_id}: {e}")
        return jsonify({"error": f"Failed to fetch totals: {str(e)}"}), 500

@app.route("/match/<event_id>/xg", methods=["GET"])
def get_match_xg(event_id):
    """Get xG (Expected Goals) analysis for a specific match on-demand"""
    try:
        home_team = request.args.get("home_team")
        away_team = request.args.get("away_team")
        league_code = request.args.get("league")
        
        if not home_team or not away_team:
            return jsonify({"error": "home_team and away_team parameters required"}), 400
        
        if not league_code:
            return jsonify({"error": "league parameter required"}), 400
        
        # Get xG prediction for the match
        xg_prediction = get_match_xg_prediction(home_team, away_team, league_code)
        
        if not xg_prediction.get('available'):
            return jsonify({
                "xg": None,
                "error": xg_prediction.get('error', 'xG data not available'),
                "source": "FBref via soccerdata"
            }), 200
        
        return jsonify({
            "xg": xg_prediction,
            "source": "FBref via soccerdata"
        })
        
    except Exception as e:
        print(f"Error fetching xG for {event_id}: {e}")
        return jsonify({
            "xg": None,
            "error": f"Failed to fetch xG data: {str(e)}",
            "source": "FBref via soccerdata"
        }), 200

def normalize_team_name(name):
    """Normalize team name for better matching"""
    if not name:
        return ""
    
    # Convert to lowercase
    normalized = name.lower()
    
    # Remove common prefixes and suffixes
    prefixes = ['fc ', 'afc ', 'cf ', 'ac ', 'sc ', 'ssc ', 'as ', 'rc ', 'rcd ', 'fk ', 'bfc ', 'vfl ', 'sv ']
    suffixes = [' fc', ' afc', ' cf', ' ac', ' sc', ' united', ' city', ' town']
    
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            break
    
    # Replace variations
    normalized = normalized.replace(' and ', ' & ')
    normalized = normalized.replace('&', 'and')
    
    # Remove extra spaces
    normalized = ' '.join(normalized.split())
    
    return normalized

def fuzzy_team_match(team1, team2):
    """Check if two team names match with fuzzy logic"""
    if not team1 or not team2:
        return False
    
    t1_lower = team1.lower()
    t2_lower = team2.lower()
    
    # Exact match
    if t1_lower == t2_lower:
        return True
    
    # Contains match
    if t1_lower in t2_lower or t2_lower in t1_lower:
        return True
    
    # Normalized match
    t1_norm = normalize_team_name(team1)
    t2_norm = normalize_team_name(team2)
    
    if t1_norm == t2_norm:
        return True
    
    # Normalized contains match
    if t1_norm in t2_norm or t2_norm in t1_norm:
        return True
    
    # Word-based match (at least 2 significant words match)
    words1 = set(t1_norm.split())
    words2 = set(t2_norm.split())
    
    # Filter out very short words (articles, etc.)
    words1 = {w for w in words1 if len(w) > 2}
    words2 = {w for w in words2 if len(w) > 2}
    
    common_words = words1 & words2
    if len(common_words) >= min(2, len(words1), len(words2)):
        return True
    
    return False

@app.route("/match/<match_id>/context", methods=["GET"])
def get_match_context(match_id):
    """Get match context including standings and form (hybrid: football-data.org primary, FBref fallback)"""
    try:
        league_code = request.args.get("league")
        home_team = request.args.get("home_team")
        away_team = request.args.get("away_team")
        
        if not league_code:
            return jsonify({"error": "league parameter required"}), 400
        
        from football_data_api import get_league_standings
        from xg_data_fetcher import fetch_fbref_league_standings
        
        try:
            # Try football-data.org first (primary source)
            standings = []
            source = None
            
            try:
                standings = get_league_standings(league_code) if league_code else []
                if standings:
                    source = "football-data.org"
            except Exception as fd_error:
                print(f"⚠️  football-data.org error: {fd_error}")
            
            # If no data from football-data.org, try FBref as fallback
            if not standings:
                print(f"📊 Trying FBref fallback for standings...")
                standings = fetch_fbref_league_standings(league_code)
                if standings:
                    source = "FBref"
            
            home_data = None
            away_data = None
            
            if standings and home_team:
                home_data = next((team for team in standings if fuzzy_team_match(team['name'], home_team)), None)
            
            if standings and away_team:
                away_data = next((team for team in standings if fuzzy_team_match(team['name'], away_team)), None)
            
            # Generate narrative based on available data
            if home_data and away_data:
                narrative = generate_match_narrative(home_data, away_data)
                if source:
                    print(f"✅ Standings from {source}")
            elif home_data or away_data:
                narrative = "Partial standings available. Full context data unavailable for this match."
            else:
                narrative = f"Standings not available for {league_code}. This may be a cup competition or teams not found in league standings."
            
            context = {
                "home_team": {
                    "position": home_data.get('position') if home_data else None,
                    "points": home_data.get('points') if home_data else None,
                    "form": home_data.get('form') if home_data else None,
                    "name": home_team
                },
                "away_team": {
                    "position": away_data.get('position') if away_data else None,
                    "points": away_data.get('points') if away_data else None,
                    "form": away_data.get('form') if away_data else None,
                    "name": away_team
                },
                "narrative": narrative,
                "has_data": bool(home_data or away_data),
                "source": source  # Track which API provided the data
            }
            
            return jsonify(context)
            
        except Exception as e:
            print(f"Error fetching context: {e}")
            return jsonify({"narrative": "Match context unavailable"}), 200
        
    except Exception as e:
        print(f"Error in match context: {e}")
        return jsonify({"error": f"Failed to fetch context: {str(e)}"}), 500

def generate_match_narrative(home_data, away_data):
    """Generate a narrative description of the match importance"""
    home_pos = home_data.get('position', 99)
    away_pos = away_data.get('position', 99)
    
    if home_pos <= 2 and away_pos <= 2:
        return "Top of the table clash between title contenders"
    elif home_pos <= 4 and away_pos <= 4:
        return "Champions League qualification battle"
    elif abs(home_pos - away_pos) <= 2:
        return "Close contest between neighboring teams in the standings"
    elif home_pos <= 3:
        return f"League leaders face mid-table opposition"
    elif away_pos <= 3:
        return f"Underdogs host league leaders"
    else:
        return "Mid-table encounter"

@app.route("/process_data", methods=["POST"])
def process_data():
    """Process all scraped match data"""
    try:
        return jsonify({"error": "Data processing via this endpoint is deprecated. Please use API-Football for data."}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

