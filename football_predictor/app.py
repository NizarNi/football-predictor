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



@app.route("/")
def index():
    """Render the home page"""
    return render_template("index.html")

@app.route("/upcoming", methods=["GET"])
def upcoming():
    """Get upcoming matches using the API-Football API"""
    league_name = request.args.get("league", None)
    season = request.args.get("season", 2025, type=int) # Default to current year
    next_n_days = request.args.get("next_n_days", 7, type=int)
    
    try:
        competitions = get_competitions()
        if not competitions:
            return jsonify({"error": "Could not fetch competitions from API-Football"}), 500

        competition_id = None
        if league_name:
            for comp in competitions:
                if comp.get("name", "").lower() == league_name.lower():
                    competition_id = comp["id"]
                    break
            if not competition_id:
                return jsonify({"error": f"League \"{league_name}\" not found in API-Football"}), 404
        else:
            # Default to a popular league if no league is specified, e.g., Premier League (ID 2021)
            default_league_id = 2021 # Premier League ID for football-data.org
            competition_id = default_league_id


        # Define a list of popular competition IDs to query
        # These IDs are based on common major leagues and can be expanded.
        # Example IDs: Premier League (2021), La Liga (2014), Serie A (2019), Bundesliga (2002), Ligue 1 (2015), Champions League (2001)
        POPULAR_COMPETITION_IDS = [2021, 2014, 2019, 2002, 2015, 2001]

        all_upcoming_matches = []
        for comp_id in POPULAR_COMPETITION_IDS:
            try:
                matches = get_upcoming_matches(comp_id, next_n_days=next_n_days)
                if matches:
                    all_upcoming_matches.extend(matches)
            except RateLimitExceededError as api_e:
                print(f"Rate limit exceeded for competition ID {comp_id}: {api_e}")
                # Continue to the next API key or competition if rate limit is hit
                continue
            except Exception as api_e:
                print(f"Error fetching matches for competition ID {comp_id}: {api_e}")
        
        # Sort matches by date
        upcoming_matches = sorted(all_upcoming_matches, key=lambda x: x["timestamp"])

        # Fetch predictions from RapidAPI for each match
        matches_with_predictions = []
        for match in upcoming_matches:
            match_id = match.get("id") # Assuming match has an 'id' field
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
                            "is_safe_bet": False # RapidAPI doesn't provide this directly
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
                        "exact_score": {} # RapidAPI doesn't provide exact score predictions in this endpoint
                    }
                except RapidAPIPredictionError as rapid_e:
                    print(f"Error fetching RapidAPI prediction for match {match_id}: {rapid_e}")
                    match["predictions"] = {"error": str(rapid_e)}
                except Exception as e:
                    print(f"Unexpected error fetching RapidAPI prediction for match {match_id}: {e}")
                    match["predictions"] = {"error": str(e)}
            matches_with_predictions.append(match)

        return jsonify({"matches": matches_with_predictions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500





@app.route("/process_data", methods=["POST"])
def process_data():
    """Process all scraped match data"""
    try:
        return jsonify({"error": "Data processing via this endpoint is deprecated. Please use API-Football for data."}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

