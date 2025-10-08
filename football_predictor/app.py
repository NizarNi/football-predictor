from flask import Flask, render_template, request, jsonify
import os
import json
from datetime import datetime
import sys

# Import our custom modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from football_data_api import get_competitions, get_upcoming_matches, RateLimitExceededError
from rapidapi_football_prediction import get_rapidapi_predictions, RapidAPIPredictionError

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
    """Get upcoming matches using the football-data.org API"""
    league_code = request.args.get("league", None)
    next_n_days = request.args.get("next_n_days", 30, type=int)
    
    try:
        # Determine which leagues to fetch
        if league_code:
            # User selected a specific league
            if league_code not in SUPPORTED_LEAGUES:
                return jsonify({"error": f"League code \"{league_code}\" not supported"}), 404
            leagues_to_fetch = [league_code]
        else:
            # Fetch from all popular leagues
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
        
        # Sort matches by date
        upcoming_matches = sorted(all_upcoming_matches, key=lambda x: x["timestamp"])

        # Fetch predictions from RapidAPI for each match
        matches_with_predictions = []
        for match in upcoming_matches:
            # Add datetime formatting for frontend
            match["datetime"] = datetime.fromtimestamp(match["timestamp"]).strftime("%Y-%m-%d %H:%M")
            
            match_id = match.get("id")
            if match_id:
                try:
                    # Fetch 'classic' (1X2) prediction
                    classic_prediction_data = get_rapidapi_predictions(match_id, market="classic")
                    classic_prediction = classic_prediction_data.get("data", {}).get("prediction")
                    classic_confidence = classic_prediction_data.get("data", {}).get("confidence")

                    # Fetch 'over_25' prediction
                    over_25_prediction_data = get_rapidapi_predictions(match_id, market="over_25")
                    over_25_prediction = over_25_prediction_data.get("data", {}).get("prediction")
                    over_25_confidence = over_25_prediction_data.get("data", {}).get("confidence")

                    # Format predictions to match existing structure
                    match["predictions"] = {
                        "1x2": {
                            "prediction": classic_prediction,
                            "confidence": classic_confidence,
                            "probabilities": {},
                            "is_safe_bet": False
                        },
                        "over_under": {
                            "2.5": {
                                "prediction": "OVER" if over_25_prediction == "yes" else "UNDER",
                                "confidence": over_25_confidence,
                                "probabilities": {},
                                "is_safe_bet": False,
                                "threshold": 2.5
                            }
                        },
                        "exact_score": {}
                    }
                    print(f"✅ Successfully fetched predictions for match {match_id}")
                except RapidAPIPredictionError as rapid_e:
                    print(f"❌ RapidAPI error for match {match_id}: {rapid_e}")
                    match["predictions"] = {
                        "error": str(rapid_e),
                        "note": "Predictions temporarily unavailable"
                    }
                except Exception as e:
                    print(f"❌ Unexpected error for match {match_id}: {e}")
                    match["predictions"] = {
                        "error": "Failed to fetch predictions",
                        "note": "Service temporarily unavailable"
                    }
            else:
                match["predictions"] = {
                    "error": "No match ID available for predictions"
                }
            
            matches_with_predictions.append(match)

        return jsonify({
            "matches": matches_with_predictions,
            "total_matches": len(matches_with_predictions)
        })
    except Exception as e:
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

