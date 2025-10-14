from flask import Flask, render_template, request
import os
import json
from datetime import datetime
import sys

from config import setup_logger
from app_utils import make_ok, make_error

# Import our custom modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# football-data.org API removed - using Understat as primary source for standings
from odds_api_client import get_upcoming_matches_with_odds, OddsAPIError, LEAGUE_CODE_MAPPING
from odds_calculator import calculate_predictions_from_odds
from xg_data_fetcher import get_match_xg_prediction
from utils import get_current_season, normalize_team_name, fuzzy_team_match

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

logger = setup_logger(__name__)

# Global variables
# Note: Matches fetched from The Odds API, standings from Understat

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
        logger.info("Handling /upcoming request", extra={
            "league": league_code,
            "next_n_days": next_n_days
        })
        # Try The Odds API first (provides both matches and odds-based predictions)
        logger.info("🔍 Fetching matches with odds from The Odds API...")
        try:
            if league_code:
                if league_code not in LEAGUE_CODE_MAPPING:
                    return make_error(
                        error=f"League code \"{league_code}\" not supported",
                        message="Invalid league code",
                        status_code=404
                    )
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
                
                logger.info("✅ Found %d matches from The Odds API", len(odds_matches))
                return make_ok({
                    "matches": odds_matches,
                    "total_matches": len(odds_matches),
                    "source": "The Odds API"
                })
        except OddsAPIError as e:
            logger.warning("⚠️  The Odds API unavailable: %s", e)
            return make_error(
                error="The Odds API is temporarily unavailable. Please try again later.",
                message="The Odds API is temporarily unavailable.",
                status_code=503
            )
        except Exception as e:
            logger.exception("⚠️  The Odds API error")
            return make_error(
                error="Unable to fetch matches. Please try again later.",
                message="Failed to fetch upcoming matches",
                status_code=500
            )

    except Exception as e:
        logger.exception("❌ Critical error")
        return make_error(
            error="Service temporarily unavailable. Please try again later.",
            message="Service temporarily unavailable",
            status_code=500
        )





@app.route("/search", methods=["POST"])
def search():
    """Search for matches by team name"""
    team_name = request.form.get("team_name", "").strip()

    if not team_name:
        return make_error(
            error="Please provide a team name",
            message="Invalid team name",
            status_code=400
        )

    try:
        logger.info("Handling /search request", extra={"team_name": team_name})
        logger.info("🔍 Searching for team: %s", team_name)

        # Use The Odds API to fetch matches from all leagues
        try:
            odds_matches = get_upcoming_matches_with_odds(
                league_codes=list(LEAGUE_CODE_MAPPING.keys()),
                next_n_days=30
            )
            
            if not odds_matches:
                # No matches from Odds API - return empty result
                logger.info("ℹ️ No matches available from The Odds API")
                return make_error(
                    error=f"No matches found for team '{team_name}' - try again later",
                    message="No matches available",
                    status_code=404
                )

            # Filter matches by team name
            team_name_lower = team_name.lower()
            filtered_matches = [
                match for match in odds_matches
                if team_name_lower in match.get("home_team", "").lower() or 
                   team_name_lower in match.get("away_team", "").lower()
            ]
            
            if not filtered_matches:
                return make_error(
                    error=f"No matches found for team '{team_name}'",
                    message="No matches found",
                    status_code=404
                )
            
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
            
            logger.info("✅ Found %d matches for '%s' from The Odds API", len(filtered_matches), team_name)
            return make_ok({
                "matches": filtered_matches,
                "source": "The Odds API"
            })

        except Exception as odds_e:
            logger.exception("⚠️ The Odds API error during search")
            return make_error(
                error="Search service temporarily unavailable",
                message="Search service temporarily unavailable",
                status_code=503
            )

    except Exception as e:
        logger.exception("Error in search")
        return make_error(
            error="Search failed. Please try again later.",
            message="Search failed",
            status_code=500
        )

@app.route("/match/<match_id>", methods=["GET"])
def get_match(match_id):
    """Get detailed information about a specific match"""
    logger.info("Handling /match request", extra={"match_id": match_id})
    # Endpoint deprecated - match details now come from The Odds API in /upcoming
    return make_error(
        error="This endpoint is deprecated. Match details are included in the /upcoming endpoint.",
        message="Endpoint deprecated",
        status_code=410
    )

@app.route("/predict/<match_id>", methods=["GET"])
def predict_match(match_id):
    """Get predictions for a specific match"""
    try:
        logger.info("Handling /predict request", extra={"match_id": match_id})
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
        
        return make_ok(response)

    except Exception as e:
        logger.exception("Error predicting match %s", match_id)
        return make_error(
            error="Unable to load predictions. Please try again later.",
            message="Prediction service error",
            status_code=500
        )

@app.route("/match/<event_id>/totals", methods=["GET"])
def get_match_totals(event_id):
    """Get over/under predictions for a specific match on-demand"""
    try:
        logger.info("Handling /match totals request", extra={"event_id": event_id})
        sport_key = request.args.get("sport_key")
        if not sport_key:
            return make_error(
                error="sport_key parameter required",
                message="Missing sport_key parameter",
                status_code=400
            )

        from odds_api_client import get_event_odds
        from odds_calculator import calculate_totals_from_odds

        odds_data = get_event_odds(sport_key, event_id, regions="us,uk,eu", markets="totals")

        if not odds_data:
            return make_error(
                error="No totals odds found for this match",
                message="No totals odds found",
                status_code=404
            )

        totals_predictions = calculate_totals_from_odds(odds_data)

        return make_ok({
            "totals": totals_predictions,
            "source": "The Odds API"
        })

    except Exception as e:
        logger.exception("Error fetching totals for %s", event_id)
        return make_error(
            error="Unable to load over/under data. Please try again later.",
            message="Failed to fetch totals",
            status_code=500
        )

@app.route("/match/<event_id>/btts", methods=["GET"])
def get_match_btts(event_id):
    """Get Both Teams To Score predictions for a specific match on-demand"""
    try:
        logger.info("Handling /match btts request", extra={"event_id": event_id})
        sport_key = request.args.get("sport_key")
        home_team = request.args.get("home_team")
        away_team = request.args.get("away_team")
        league_code = request.args.get("league")

        if not sport_key:
            return make_error(
                error="sport_key parameter required",
                message="Missing sport_key parameter",
                status_code=400
            )

        from odds_api_client import get_event_odds
        from odds_calculator import calculate_btts_from_odds, calculate_btts_probability_from_xg

        # Fetch BTTS odds from The Odds API
        odds_data = get_event_odds(sport_key, event_id, regions="us,uk,eu", markets="btts")

        if not odds_data:
            return make_error(
                error="No BTTS odds found for this match",
                message="No BTTS odds found",
                status_code=404
            )
        
        # Calculate market consensus from bookmakers
        btts_market = calculate_btts_from_odds(odds_data)
        
        # Get xG-based prediction if xG data available
        # NOTE: BTTS needs TRUE defensive xGA from Understat, not FBref's PSxGA (goalkeeper metric)
        btts_xg = None
        if home_team and away_team and league_code:
            try:
                # Get offensive xG from FBref
                xg_prediction = get_match_xg_prediction(home_team, away_team, league_code)
                
                # Get defensive xGA from Understat context (TRUE defensive metric, not goalkeeper PSxGA)
                from understat_client import fetch_understat_standings
                current_season = get_current_season()
                standings = fetch_understat_standings(league_code, current_season)
                
                home_xg_per_game = None
                away_xg_per_game = None
                home_xga_per_game = None
                away_xga_per_game = None
                
                # Get offensive xG/game from FBref
                if xg_prediction.get('available') and xg_prediction.get('xg'):
                    home_xg_per_game = xg_prediction['xg'].get('home_stats', {}).get('xg_for_per_game')
                    away_xg_per_game = xg_prediction['xg'].get('away_stats', {}).get('xg_for_per_game')
                
                # Get defensive xGA/game from Understat standings (NOT PSxGA)
                if standings:
                    home_standings = next((team for team in standings if fuzzy_team_match(team['name'], home_team)), None)
                    away_standings = next((team for team in standings if fuzzy_team_match(team['name'], away_team)), None)
                    
                    if home_standings and home_standings.get('xGA') is not None and home_standings.get('played', 0) > 0:
                        home_xga_per_game = home_standings['xGA'] / home_standings['played']
                    
                    if away_standings and away_standings.get('xGA') is not None and away_standings.get('played', 0) > 0:
                        away_xga_per_game = away_standings['xGA'] / away_standings['played']
                    
                if all([x is not None for x in [home_xg_per_game, away_xg_per_game, home_xga_per_game, away_xga_per_game]]):
                    btts_xg = calculate_btts_probability_from_xg(
                        home_xg_per_game,
                        away_xg_per_game,
                        home_xga_per_game,
                        away_xga_per_game
                    )
            except Exception as e:
                logger.warning("⚠️  Could not calculate xG-based BTTS: %s", e)
                btts_xg = None
        
        return make_ok({
            "btts": {
                "market": btts_market,
                "xg_model": btts_xg
            },
            "source": "The Odds API + xG Analysis"
        })

    except Exception as e:
        logger.exception("Error fetching BTTS for %s", event_id)
        return make_error(
            error="Unable to load BTTS data. Please try again later.",
            message="Failed to fetch BTTS data",
            status_code=500
        )

@app.route("/match/<event_id>/xg", methods=["GET"])
def get_match_xg(event_id):
    """Get xG (Expected Goals) analysis for a specific match on-demand"""
    try:
        logger.info("Handling /match xg request", extra={"event_id": event_id})
        home_team = request.args.get("home_team")
        away_team = request.args.get("away_team")
        league_code = request.args.get("league")

        if not home_team or not away_team:
            return make_error(
                error="home_team and away_team parameters required",
                message="Missing team parameters",
                status_code=400
            )

        if not league_code:
            return make_error(
                error="league parameter required",
                message="Missing league parameter",
                status_code=400
            )

        # Get xG prediction for the match
        xg_prediction = get_match_xg_prediction(home_team, away_team, league_code)

        if not xg_prediction.get('available'):
            return make_ok({
                "xg": None,
                "error": xg_prediction.get('error', 'xG data not available'),
                "source": "FBref via soccerdata"
            })

        return make_ok({
            "xg": xg_prediction,
            "source": "FBref via soccerdata"
        })

    except Exception as e:
        logger.exception("Error fetching xG for %s", event_id)
        return make_error(
            error="Unable to load xG data. Please try again later.",
            message="Failed to fetch xG data",
            status_code=200
        )

@app.route("/career_xg", methods=["GET"])
def get_career_xg():
    """Get career xG statistics (2010-2025) for a team"""
    try:
        logger.info("Handling /career_xg request")
        team = request.args.get("team")
        league = request.args.get("league")

        if not team or not league:
            return make_error(
                error="team and league parameters required",
                message="Missing team or league parameter",
                status_code=400
            )

        from xg_data_fetcher import fetch_career_xg_stats

        career_stats = fetch_career_xg_stats(team, league)

        if not career_stats:
            return make_ok({
                "career_xg": None,
                "error": "No historical xG data available for this team",
                "source": "FBref (2010-2025)"
            })

        return make_ok({
            "career_xg": career_stats,
            "source": "FBref (2010-2025)"
        })

    except Exception as e:
        logger.exception("Error fetching career xG")
        return make_error(
            error="Unable to load career xG data",
            message="Failed to fetch career xG",
            status_code=200
        )

@app.route("/match/<match_id>/context", methods=["GET"])
def get_match_context(match_id):
    """Get match context including standings, form, and Elo ratings"""
    try:
        logger.info("Handling /match context request", extra={"match_id": match_id})
        league_code = request.args.get("league")
        home_team = request.args.get("home_team")
        away_team = request.args.get("away_team")

        if not league_code:
            return make_error(
                error="league parameter required",
                message="Missing league parameter",
                status_code=400
            )

        from understat_client import fetch_understat_standings
        from elo_client import get_team_elo, calculate_elo_probabilities

        try:
            # Use Understat as primary source for standings with dynamic season
            current_season = get_current_season()
            logger.info("📊 Fetching standings from Understat", extra={"season": current_season})
            standings = fetch_understat_standings(league_code, current_season)
            source = "Understat" if standings else None

            # Fetch Elo ratings for both teams
            logger.info("🎯 Fetching Elo ratings from ClubElo")
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
                    logger.info("✅ Standings fetched", extra={"source": source})
            elif home_data or away_data:
                narrative = "Partial standings available. Full context data unavailable for this match."
            else:
                narrative = f"Standings not available for {league_code}. This may be a cup competition or teams not found in league standings."
            
            # Calculate season display string
            season_start = current_season - 1
            season_display = f"{season_start}/{str(current_season)[-2:]}"
            
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
                "source": source,
                "season_display": season_display
            }

            if elo_probs:
                logger.info(
                    "✅ Elo predictions computed",
                    extra={
                        "home_win": elo_probs['home_win'],
                        "draw": elo_probs['draw'],
                        "away_win": elo_probs['away_win']
                    }
                )

            return make_ok(context)

        except Exception as e:
            logger.exception("Error fetching context for %s", match_id)
            return make_ok({"narrative": "Match context unavailable"})

    except Exception as e:
        logger.exception("Error in match context for %s", match_id)
        return make_error(
            error="Unable to load match context. Please try again later.",
            message="Failed to fetch match context",
            status_code=500
        )

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
        logger.info("Handling /process_data request")
        return make_error(
            error="Data processing via this endpoint is deprecated. Please use API-Football for data.",
            message="Endpoint deprecated",
            status_code=400
        )
    except Exception as e:
        logger.exception("Error handling /process_data request")
        return make_error(
            error="Service error. Please try again later.",
            message="Service error",
            status_code=500
        )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

