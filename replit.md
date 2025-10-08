# Football Prediction - Safe Bet Analyzer

## Overview
A Flask-based web application that provides football match predictions using external APIs. The application fetches upcoming matches from the football-data.org API and generates predictions using the Football Prediction API on RapidAPI.

## Recent Changes
- **2025-10-08**: Fixed infinite loop bug and added API key rotation
  - **FIXED**: Implemented `/match/<id>` endpoint to return match details in correct frontend structure
  - **FIXED**: Implemented `/predict/<id>` endpoint with placeholder predictions
  - **FIXED**: Critical bug in `get_match_details()` - API returns match data directly, not wrapped in "match" key
  - **ADDED**: RapidAPI key rotation support using `RAPIDAPI_KEY` and `RAPIDAPI_KEY_2` for rate limit handling
  - **IMPROVED**: API key rotation logic with round-robin selection across multiple keys
  - **TESTED**: Complete user flow: click league → see matches → click match → see predictions (no longer infinite loop)

- **2025-10-08**: Initial Replit setup completed
  - Installed Python 3.11 and dependencies (Flask, gunicorn, requests)
  - Removed hardcoded API keys for security (now using Replit Secrets)
  - Fixed syntax errors and import issues in Python files
  - Configured development workflow to run on port 5000
  - Configured deployment with gunicorn for production
  - Created .gitignore for Python project

## Project Architecture

### Structure
```
football_predictor/
├── app.py                      # Main Flask application
├── football_data_api.py        # API client for football-data.org
├── rapidapi_football_prediction.py  # RapidAPI prediction client
├── gunicorn_config.py          # Gunicorn production configuration
├── start.sh                    # Startup script
├── requirements.txt            # Python dependencies
├── templates/
│   └── index.html             # Main web interface
└── src/
    ├── main.py
    └── user_input_scraper.py
```

### Key Components
1. **Flask App (app.py)**: Main application with endpoints for:
   - `/` - Home page with match search interface
   - `/upcoming` - Fetch upcoming matches from multiple leagues (with dual-API fallback)
   - `/match/<id>` - Get detailed match information by ID
   - `/predict/<id>` - Get predictions for a specific match (returns placeholder when unavailable)
   - `/search` - Search matches by team name
   - `/process_data` - Deprecated endpoint (returns error)

2. **Football Data API (football_data_api.py)**: 
   - Fetches competitions and matches from football-data.org
   - Implements API key rotation to handle rate limits
   - Supports multiple API keys for high availability

3. **RapidAPI Predictions (rapidapi_football_prediction.py)**:
   - Fetches match predictions from Football Prediction API
   - Supports different prediction markets (classic, over_25)
   - **NEW**: Implements API key rotation with round-robin selection
   - **NEW**: Automatic failover between multiple RapidAPI keys

4. **Frontend (templates/index.html)**:
   - Bootstrap-based responsive UI
   - Team search functionality
   - League browsing (Premier League, La Liga, Bundesliga, etc.)
   - Prediction display with confidence scores

### API Keys Required
The application requires the following API keys (configured in Replit Secrets):
- `FOOTBALL_DATA_API_KEY_1` - Primary football-data.org API key
- `FOOTBALL_DATA_API_KEY_2` - Secondary football-data.org API key
- `FOOTBALL_DATA_API_KEY_3` - Tertiary football-data.org API key
- `RAPIDAPI_KEY` - Primary RapidAPI key for predictions
- `RAPIDAPI_KEY_2` - Secondary RapidAPI key for rate limit rotation

### Dependencies
- Flask 3.1.2 - Web framework
- gunicorn 21.2.0 - WSGI HTTP server for production
- requests 2.31.0 - HTTP library for API calls

## Development

### Running Locally
The app runs automatically via the configured workflow:
```bash
cd football_predictor && python app.py
```
The development server runs on `http://0.0.0.0:5000`

### Production Deployment
The app is configured to deploy using gunicorn with:
- 4 worker processes
- 120-second timeout
- Port 5000 binding
- Auto-scaling deployment type

## Features
- **Match Predictions**: Get predictions for upcoming football matches
- **Multiple Prediction Types**:
  - 1X2 (Home Win/Draw/Away Win)
  - Over/Under goals (various thresholds)
  - Exact score predictions
- **Confidence Levels**: Each prediction includes a confidence score
- **Multi-League Support**: Fetches matches from multiple top European leagues
- **Rate Limit Handling**: Automatic API key rotation to handle rate limits

## Supported Leagues
- Premier League (England)
- La Liga (Spain)
- Serie A (Italy)
- Bundesliga (Germany)
- Ligue 1 (France)
- Champions League

## Technical Notes
- The app uses Flask in debug mode for development
- Production uses gunicorn with 4 workers
- API calls include 1-second delays to avoid rate limiting
- Up to 5 retries with automatic key rotation on rate limits
- Bootstrap 5.3 for responsive UI design
