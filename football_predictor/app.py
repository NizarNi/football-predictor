from flask import Flask, render_template, request, jsonify
import os
import json
from datetime import datetime
import sys

# Import our custom modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from football_data_api import get_competitions, get_upcoming_matches, RateLimitExceededError
from rapidapi_football_prediction import get_upcoming_matches_with_predictions, RapidAPIPredictionError

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

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
SUPPORTED_LEAGUES = ["PL", "PD", "BL1", "SA", "FL1", "CL"]



@app.route("/")
def index():
    """Render the home page"""
    return render_template("index.html")

@app.route("/upcoming", methods=["GET"])
def upcoming():
    """Get upcoming matches with predictions using RapidAPI (primary) and football-data.org (fallback)"""
    league_code = request.args.get("league", None)
    next_n_days = request.args.get("next_n_days", 30, type=int)
    
    try:
        # Try RapidAPI first (provides both matches and predictions)
        print(f"🔍 Fetching matches with predictions from RapidAPI...")
        try:
            rapid_matches = get_upcoming_matches_with_predictions(next_n_days=next_n_days, federation="UEFA")
            
            # Filter by league if specified
            if league_code and rapid_matches:
                # Map league codes to competition names (approximate matching)
                league_filters = {
                    "PL": ["premier league", "england"],
                    "PD": ["la liga", "spain"],
                    "BL1": ["bundesliga", "germany"],
                    "SA": ["serie a", "italy"],
                    "FL1": ["ligue 1", "france"],
                    "CL": ["champions league", "uefa"]
                }
                filter_terms = league_filters.get(league_code, [league_code.lower()])
                rapid_matches = [
                    m for m in rapid_matches 
                    if any(term in m.get("league", "").lower() for term in filter_terms)
                ]
            
            if rapid_matches:
                print(f"✅ Found {len(rapid_matches)} matches from RapidAPI")
                return jsonify({
                    "matches": rapid_matches,
                    "total_matches": len(rapid_matches),
                    "source": "RapidAPI"
                })
        except RapidAPIPredictionError as e:
            print(f"⚠️  RapidAPI unavailable: {e}")
        except Exception as e:
            print(f"⚠️  RapidAPI error: {e}")
        
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
        # Fetch matches from all leagues
        all_upcoming_matches = []
        
        for league in SUPPORTED_LEAGUES:
            try:
                matches = get_upcoming_matches(league, next_n_days=30)
                if matches:
                    all_upcoming_matches.extend(matches)
            except RateLimitExceededError as api_e:
                print(f"Rate limit exceeded for {league}: {api_e}")
                continue
            except Exception as api_e:
                print(f"Error fetching matches for {league}: {api_e}")
        
        # Filter matches by team name
        team_name_lower = team_name.lower()
        filtered_matches = [
            match for match in all_upcoming_matches
            if team_name_lower in match.get("home_team", "").lower() or 
               team_name_lower in match.get("away_team", "").lower()
        ]
        
        if not filtered_matches:
            return jsonify({"error": f"No matches found for team '{team_name}'"}), 404
        
        # Sort by date
        filtered_matches = sorted(filtered_matches, key=lambda x: x["timestamp"])
        
        # Add datetime formatting for frontend
        for match in filtered_matches:
            match["datetime"] = datetime.fromtimestamp(match["timestamp"]).strftime("%Y-%m-%d %H:%M")
        
        return jsonify({"matches": filtered_matches})
        
    except Exception as e:
        print(f"Error in search: {e}")
        return jsonify({"error": f"Search failed: {str(e)}"}), 500

@app.route("/process_data", methods=["POST"])
def process_data():
    """Process all scraped match data"""
    try:
        return jsonify({"error": "Data processing via this endpoint is deprecated. Please use API-Football for data."}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

