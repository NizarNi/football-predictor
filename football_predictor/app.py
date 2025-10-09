from flask import Flask, render_template, request, jsonify
import os
import json
from datetime import datetime
import sys

# Import our custom modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# football-data.org API removed - using Understat as primary source for standings
from odds_api_client import get_upcoming_matches_with_odds, OddsAPIError, LEAGUE_CODE_MAPPING
from odds_calculator import calculate_predictions_from_odds
from xg_data_fetcher import get_match_xg_prediction

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Global variables
# Note: Matches fetched from The Odds API, standings from Understat

def get_current_season():
    """
    Calculate current football season based on calendar month.
    Football seasons run August to May:
    - August-December (months 8-12): Use current year as season (e.g., Oct 2025 → Season 2025)
    - January-July (months 1-7): Use previous year as season (e.g., Jan 2026 → Season 2025)
    """
    today = datetime.now()
    return today.year if today.month >= 8 else today.year - 1

@app.route("/")
def index():
    """Render the home page"""
    return render_template("index.html")

@app.route("/learn")
def learn():
    """Educational page about football analytics and betting strategies"""
    return render_template("learn.html")

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
                # Import Elo client for predictions
                from elo_client import get_team_elo, calculate_elo_probabilities
                
                # Calculate predictions from odds for each match
                for match in odds_matches:
                    predictions = calculate_predictions_from_odds(match)
                    
                    # Format match data
                    match["datetime"] = match["commence_time"]
                    match["timestamp"] = datetime.fromisoformat(match["commence_time"].replace('Z', '+00:00')).timestamp()
                    
                    # Add Elo predictions
                    home_team = match.get("home_team")
                    away_team = match.get("away_team")
                    if home_team and away_team:
                        home_elo = get_team_elo(home_team)
                        away_elo = get_team_elo(away_team)
                        if home_elo and away_elo:
                            match["elo_predictions"] = calculate_elo_probabilities(home_elo, away_elo)
                    
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
            return jsonify({"error": f"The Odds API unavailable: {str(e)}"}), 503
        except Exception as e:
            print(f"⚠️  The Odds API error: {e}")
            return jsonify({"error": f"Unable to fetch matches: {str(e)}"}), 500
        
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
    # Endpoint deprecated - match details now come from The Odds API in /upcoming
    return jsonify({"error": "This endpoint is deprecated. Match details are included in the /upcoming endpoint."}), 410

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
    """Get match context including standings, form, and Elo ratings"""
    try:
        league_code = request.args.get("league")
        home_team = request.args.get("home_team")
        away_team = request.args.get("away_team")
        
        if not league_code:
            return jsonify({"error": "league parameter required"}), 400
        
        from understat_client import fetch_understat_standings
        from elo_client import get_team_elo, calculate_elo_probabilities
        
        try:
            # Use Understat as primary source for standings with dynamic season
            current_season = get_current_season()
            print(f"📊 Fetching standings from Understat for season {current_season}...")
            standings = fetch_understat_standings(league_code, current_season)
            source = "Understat" if standings else None
            
            # Fetch Elo ratings for both teams
            print(f"🎯 Fetching Elo ratings from ClubElo...")
            home_elo = get_team_elo(home_team) if home_team else None
            away_elo = get_team_elo(away_team) if away_team else None
            
            # Calculate Elo-based probabilities
            elo_probs = calculate_elo_probabilities(home_elo, away_elo) if home_elo and away_elo else None
            
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
                    "name": home_team,
                    "ppda_coef": home_data.get('ppda_coef') if home_data else None,
                    "oppda_coef": home_data.get('oppda_coef') if home_data else None,
                    "xG": home_data.get('xG') if home_data else None,
                    "xGA": home_data.get('xGA') if home_data else None,
                    "elo_rating": home_elo,
                    "played": home_data.get('match_count', home_data.get('played', 0)) if home_data else 0,
                    "xg_percentile": home_data.get('xg_percentile') if home_data else None,
                    "xga_percentile": home_data.get('xga_percentile') if home_data else None,
                    "ppda_percentile": home_data.get('ppda_percentile') if home_data else None,
                    "attack_rating": home_data.get('attack_rating') if home_data else None,
                    "defense_rating": home_data.get('defense_rating') if home_data else None,
                    "league_stats": home_data.get('league_stats') if home_data else None,
                    "recent_trend": home_data.get('recent_trend') if home_data else None
                },
                "away_team": {
                    "position": away_data.get('position') if away_data else None,
                    "points": away_data.get('points') if away_data else None,
                    "form": away_data.get('form') if away_data else None,
                    "name": away_team,
                    "ppda_coef": away_data.get('ppda_coef') if away_data else None,
                    "oppda_coef": away_data.get('oppda_coef') if away_data else None,
                    "xG": away_data.get('xG') if away_data else None,
                    "xGA": away_data.get('xGA') if away_data else None,
                    "elo_rating": away_elo,
                    "played": away_data.get('match_count', away_data.get('played', 0)) if away_data else 0,
                    "xg_percentile": away_data.get('xg_percentile') if away_data else None,
                    "xga_percentile": away_data.get('xga_percentile') if away_data else None,
                    "ppda_percentile": away_data.get('ppda_percentile') if away_data else None,
                    "attack_rating": away_data.get('attack_rating') if away_data else None,
                    "defense_rating": away_data.get('defense_rating') if away_data else None,
                    "league_stats": away_data.get('league_stats') if away_data else None,
                    "recent_trend": away_data.get('recent_trend') if away_data else None
                },
                "elo_predictions": elo_probs,
                "narrative": narrative,
                "has_data": bool(home_data or away_data),
                "source": source
            }
            
            if elo_probs:
                print(f"✅ Elo predictions: Home {elo_probs['home_win']*100:.1f}% | Draw {elo_probs['draw']*100:.1f}% | Away {elo_probs['away_win']*100:.1f}%")
            
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

