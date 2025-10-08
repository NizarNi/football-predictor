
from flask import Flask, render_template, request, jsonify
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
import sys

# Import our custom modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from user_input_scraper import search_matches_sync, get_match_data_sync, get_upcoming_matches_sync
from preprocess_flashscore_data import extract_features, create_feature_vectors
from neural_network_model import SafeBetPredictor, OverUnderPredictor, ExactScorePredictor

app = Flask(__name__)

# Create directories if they don't exist
os.makedirs('scraped_data', exist_ok=True)
os.makedirs('processed_data', exist_ok=True)
os.makedirs('models', exist_ok=True)
os.makedirs('static', exist_ok=True)
os.makedirs('templates', exist_ok=True)

# Global variables
MODELS_LOADED = False
model_1x2 = None
model_over_under_05 = None
model_over_under_15 = None
model_over_under_25 = None
model_over_under_35 = None
model_exact_score = None

def load_models():
    """Load all prediction models if available"""
    global MODELS_LOADED, model_1x2, model_over_under_05, model_over_under_15, model_over_under_25, model_over_under_35, model_exact_score
    
    try:
        # Load 1X2 model
        model_1x2 = SafeBetPredictor(model_name="safe_bet_1x2_model")
        model_1x2.load()
        
        # Load Over/Under models
        model_over_under_05 = OverUnderPredictor(threshold=0.5)
        model_over_under_05.load()
        
        model_over_under_15 = OverUnderPredictor(threshold=1.5)
        model_over_under_15.load()
        
        model_over_under_25 = OverUnderPredictor(threshold=2.5)
        model_over_under_25.load()
        
        model_over_under_35 = OverUnderPredictor(threshold=3.5)
        model_over_under_35.load()
        
        # Load Exact Score model
        model_exact_score = ExactScorePredictor()
        model_exact_score.load()
        
        MODELS_LOADED = True
        print("All models loaded successfully")
        return True
    except Exception as e:
        print(f"Error loading models: {e}")
        MODELS_LOADED = False
        return False

# Try to load models at startup
try:
    load_models()
except Exception as e:
    print(f"Could not load models at startup: {e}")
    print("Models will need to be trained before predictions can be made")

@app.route('/')
def index():
    """Render the home page"""
    return render_template('index.html', models_loaded=MODELS_LOADED)

@app.route('/search', methods=['POST'])
def search():
    """Search for matches by team name"""
    team_name = request.form.get('team_name', '')
    
    if not team_name:
        return jsonify({'error': 'No team name provided'}), 400
    
    try:
        search_results = search_matches_sync(team_name)
        return jsonify({'matches': search_results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upcoming', methods=['GET'])
def upcoming():
    """Get upcoming matches"""
    league = request.args.get('league', None)
    
    try:
        upcoming_matches = get_upcoming_matches_sync(league_name=league)
        return jsonify({'matches': upcoming_matches})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/match/<match_id>', methods=['GET'])
def get_match(match_id):
    """Get detailed data for a specific match"""
    try:
        # Check if we already have data for this match
        cache_file = os.path.join('scraped_data', f'match_{match_id}.json')
        
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                match_data = json.load(f)
        else:
            match_data = get_match_data_sync(match_id)
            
            # Cache the data
            with open(cache_file, 'w') as f:
                json.dump(match_data, f, indent=2)
        
        return jsonify({'match': match_data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/predict/<match_id>', methods=['GET'])
def predict(match_id):
    """Make predictions for a specific match"""
    if not MODELS_LOADED:
        return jsonify({'error': 'Models not loaded. Please train models first.'}), 400
    
    try:
        # Get match data
        cache_file = os.path.join('scraped_data', f'match_{match_id}.json')
        
        if not os.path.exists(cache_file):
            return jsonify({'error': 'Match data not found. Please fetch match data first.'}), 404
        
        with open(cache_file, 'r') as f:
            match_data = json.load(f)
        
        # Extract features
        features = extract_features(match_data)
        
        if not features:
            return jsonify({'error': 'Could not extract features from match data'}), 500
        
        # Create feature vector
        X = pd.DataFrame([features])
        
        # Make predictions
        predictions = {}
        
        # 1X2 prediction
        try:
            safe_bets = model_1x2.get_safe_bets(X)
            predictions['1x2'] = safe_bets[0] if safe_bets else None
        except Exception as e:
            print(f"Error making 1X2 prediction: {e}")
            predictions['1x2'] = None
        
        # Over/Under predictions
        try:
            ou_predictions = {}
            
            # Over/Under 0.5
            ou_05_bets = model_over_under_05.get_safe_bets(X)
            ou_predictions['0.5'] = ou_05_bets[0] if ou_05_bets else None
            
            # Over/Under 1.5
            ou_15_bets = model_over_under_15.get_safe_bets(X)
            ou_predictions['1.5'] = ou_15_bets[0] if ou_15_bets else None
            
            # Over/Under 2.5
            ou_25_bets = model_over_under_25.get_safe_bets(X)
            ou_predictions['2.5'] = ou_25_bets[0] if ou_25_bets else None
            
            # Over/Under 3.5
            ou_35_bets = model_over_under_35.get_safe_bets(X)
            ou_predictions['3.5'] = ou_35_bets[0] if ou_35_bets else None
            
            predictions['over_under'] = ou_predictions
        except Exception as e:
            print(f"Error making Over/Under predictions: {e}")
            predictions['over_under'] = None
        
        # Exact Score prediction
        try:
            score_predictions = model_exact_score.get_top_predictions(X, top_k=5)
            predictions['exact_score'] = score_predictions[0] if score_predictions else None
        except Exception as e:
            print(f"Error making Exact Score prediction: {e}")
            predictions['exact_score'] = None
        
        # Add match info to predictions
        predictions['match_info'] = {
            'home_team': match_data.get('home', {}).get('name', 'Unknown'),
            'away_team': match_data.get('away', {}).get('name', 'Unknown'),
            'date': match_data.get('date', 'Unknown'),
            'league': match_data.get('stage', 'Unknown')
        }
        
        return jsonify({'predictions': predictions})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/train', methods=['POST'])
def train_models():
    """Train prediction models using available data"""
    try:
        from neural_network_model import train_models
        
        # Check if we have processed data
        data_path = os.path.join('processed_data', 'processed_match_data.csv')
        
        if not os.path.exists(data_path):
            return jsonify({'error': 'No processed data available for training'}), 400
        
        # Train models
        train_models(data_path)
        
        # Load the trained models
        success = load_models()
        
        if success:
            return jsonify({'success': 'Models trained and loaded successfully'})
        else:
            return jsonify({'error': 'Models trained but could not be loaded'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process_data', methods=['POST'])
def process_data():
    """Process all scraped match data"""
    try:
        from preprocess_flashscore_data import preprocess_match_data, preprocess_upcoming_matches
        
        # Process match data
        match_df = preprocess_match_data()
        
        # Process upcoming matches
        upcoming_df = preprocess_upcoming_matches()
        
        if match_df is not None:
            return jsonify({'success': f'Processed {len(match_df)} matches'} if not match_df.empty else 'No match data was processed')
        else:
            return jsonify({'warning': 'No match data was processed'}) # This line will be reached if match_df is None
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

