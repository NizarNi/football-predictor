# Football Prediction - Safe Bet Analyzer

## Overview
A Flask-based web application that provides football match predictions using real bookmaker odds from The Odds API. The application fetches upcoming matches with live odds from 30+ bookmakers, converts odds to implied probabilities, detects arbitrage opportunities, and provides consensus predictions based on market data.

## Recent Changes
- **2025-10-08**: Advanced Betting Analysis & UX Improvements (Latest)
  - **NEW FEATURE**: On-demand Betting Analysis button (saves page load time, displays arbitrage/tips on click)
  - **ENHANCED**: Arbitrage display now shows bookmaker names and odds for each stake (e.g., "Home: $40.05 @ Betfair (2.50)")
  - **FILTERED**: Over/Under predictions to only show common lines (1.5, 2.5, 3.5 goals) - hides exotic Asian handicap lines
  - **NEW FEATURE**: Intelligent betting tips with risk-based recommendations (Safest 60-80%, Balanced 30-50%, Value 15-30%)
  - **IMPROVED**: Match Context error handling - shows partial data gracefully when teams not found in standings
  - **NEW FEATURE**: Autocomplete search with 30+ teams supporting nicknames (PSG→Paris Saint Germain, Barca→Barcelona, Bayern→Bayern Munich)
  - **ENHANCED**: Alias normalization - typing "PSG" and pressing Enter now correctly searches for "Paris Saint Germain"
  - **UX**: Autocomplete dropdown shows team name, matched alias, and league with 8-result limit

- **2025-10-08**: UI Bug Fixes and Code Cleanup
  - **REMOVED**: Exact Score component that was causing endless API loops (service not offered by The Odds API)
  - **REMOVED**: Dead fallback code - getMatchDetails(), getPredictions(), displayExactScorePrediction() functions
  - **FIXED**: Over/Under button scope issue - exposed loadOverUnderPredictions to global window object for inline onclick handler
  - **ENHANCED**: Match Context display with colored form indicators (🟩 Win, ⬜ Draw, 🟥 Loss) replacing plain text
  - **IMPROVED**: Match Context table layout for better readability with team positions and points
  - **CODE CLEANUP**: Removed all references to removed components and unused endpoints

- **2025-10-08**: On-Demand Over/Under Predictions & Match Context
  - **ADDED**: `/match/<event_id>/totals` endpoint for on-demand Over/Under odds fetching
  - **ADDED**: `calculate_totals_from_odds()` function to process totals market data
  - **ADDED**: `/match/<match_id>/context` endpoint for league standings and team form
  - **ADDED**: `get_league_standings()` function to fetch standings from football-data.org
  - **ADDED**: `generate_match_narrative()` to create contextual match descriptions
  - **NEW FEATURE**: "Show Over/Under Odds" button loads totals only when clicked (saves 50% API quota)
  - **NEW FEATURE**: Match Context panel displays team positions, points, and form automatically
  - **IMPROVED**: Over/Under predictions show multiple lines (2.5, 3.5 goals) with consensus probabilities
  - **COST OPTIMIZATION**: Deferred totals fetching reduces API calls from 3 markets to 1 market per match view

- **2025-10-08**: Major Architecture Update - The Odds API Integration
  - **REPLACED**: RapidAPI predictions with The Odds API real bookmaker odds
  - **ADDED**: `odds_api_client.py` for fetching odds from The Odds API with 3-key rotation
  - **ADDED**: `odds_calculator.py` for odds-to-probability conversion and arbitrage detection
  - **REMOVED**: `rapidapi_football_prediction.py` - no longer needed
  - **ENHANCED**: Predictions now based on averaged bookmaker consensus
  - **NEW FEATURE**: Arbitrage opportunity detection when total probability < 100%
  - **NEW FEATURE**: Best odds display showing highest prices from any bookmaker
  - **IMPROVED**: API key rotation system now supports 3 keys for extended quota
  - **METHODOLOGY**: Sports-betting approach using real market data instead of ML predictions

- **2025-10-08**: UI Enhancements - Europa League & Popular Match Highlighting
  - **ADDED**: Europa League (EL) support to both backend and frontend
  - **ADDED**: Popular match highlighting with golden badge for Champions League and Europa League fixtures
  - **IMPROVED**: Search bar with better placeholder text and helper instructions
  - **STYLED**: Match cards for UEFA competitions now display ⭐ POPULAR badge with golden gradient border

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
├── football_data_api.py        # API client for football-data.org (fallback)
├── odds_api_client.py          # The Odds API client with key rotation
├── odds_calculator.py          # Odds conversion and arbitrage detection
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
   - `/match/<event_id>/totals` - On-demand Over/Under odds fetching (saves API quota)
   - `/match/<match_id>/context` - League standings and team form with narrative generation
   - `/search` - Search matches by team name
   - `/process_data` - Deprecated endpoint (returns error)

2. **Football Data API (football_data_api.py)**: 
   - Fallback source for match schedules from football-data.org
   - Implements API key rotation to handle rate limits
   - Supports multiple API keys for high availability

3. **The Odds API Client (odds_api_client.py)**:
   - Fetches live odds from 30+ bookmakers via The Odds API
   - Maps league codes (PL, PD, BL1, etc.) to Odds API sport keys
   - Implements 3-key rotation for extended API quota
   - Supports multiple regions (US, UK, EU) and markets (h2h, spreads, totals)

4. **Odds Calculator (odds_calculator.py)**:
   - Converts decimal/American odds to implied probabilities
   - Averages probabilities across all bookmakers for consensus
   - Detects arbitrage opportunities (when combined probability < 100%)
   - Finds best odds for each outcome across all bookmakers
   - Calculates optimal stake distribution for arbitrage bets

5. **Frontend (templates/index.html)**:
   - Bootstrap-based responsive UI
   - Team search functionality
   - League browsing (Premier League, La Liga, Bundesliga, etc.)
   - Prediction display with confidence scores

### API Keys Required
The application requires the following API keys (configured in Replit Secrets):
- `FOOTBALL_DATA_API_KEY_1` - Primary football-data.org API key (fallback)
- `FOOTBALL_DATA_API_KEY_2` - Secondary football-data.org API key (fallback)
- `FOOTBALL_DATA_API_KEY_3` - Tertiary football-data.org API key (fallback)
- `ODDS_API_KEY_1` - Primary The Odds API key for live odds
- `ODDS_API_KEY_2` - Secondary The Odds API key for rate limit rotation
- `ODDS_API_KEY_3` - Tertiary The Odds API key for extended quota

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
- **Odds-Based Predictions**: Get predictions based on real bookmaker consensus
- **Bookmaker Consensus**: Averaged probabilities across 30+ bookmakers
- **Arbitrage Detection**: Automatically identifies arbitrage opportunities with profit margins
- **Best Odds Display**: Shows best available odds for each outcome across all bookmakers
- **Prediction Types**:
  - 1X2 (Home Win/Draw/Away Win) with implied probabilities
  - Confidence scores based on market consensus
  - Bookmaker count for transparency
- **Multi-League Support**: 
  - Premier League (PL)
  - La Liga (PD)
  - Bundesliga (BL1)
  - Serie A (SA)
  - Ligue 1 (FL1)
  - Champions League (CL)
  - Europa League (EL)
- **Rate Limit Handling**: Automatic 3-key rotation to handle API quotas
- **Real Market Data**: Uses actual bookmaker odds, not ML predictions

## Supported Leagues
- Premier League (England)
- La Liga (Spain)
- Serie A (Italy)
- Bundesliga (Germany)
- Ligue 1 (France)
- Champions League
- Europa League

## Technical Notes
- The app uses Flask in debug mode for development
- Production uses gunicorn with 4 workers
- API calls include 1-second delays to avoid rate limiting
- Up to 5 retries with automatic key rotation on rate limits
- Bootstrap 5.3 for responsive UI design
