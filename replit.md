# Football Prediction - Safe Bet Analyzer

## Overview
A Flask-based web application providing football match predictions using real bookmaker odds. It fetches upcoming matches and live odds, converts odds to implied probabilities, detects arbitrage opportunities, and offers consensus predictions based on market data. The project aims to empower users with data-driven insights for sports betting, covering key European leagues and competitions.

## User Preferences
I prefer detailed explanations. Ask before making major changes. I want iterative development. I prefer simple language.

## System Architecture

### UI/UX Decisions
- **Responsive Design:** Utilizes Bootstrap for responsiveness, with an optimized layout for desktop and mobile.
- **Search & Filtering:** Features a prominent, centered search bar with autocomplete and a unified horizontal filter bar for bet opportunities and arbitrage.
- **Visual Cues:** Dynamic badges, team logos, colored form indicators (Win, Draw, Loss), and an arbitrage badge with visual emphasis.
- **Enhanced Tooltips:** Comprehensive tooltips for xG, Elo ratings, and PPDA, styled for readability and dynamic content.
- **Dark Mode:** Complete dark theme with a toggle, localStorage persistence, and theme-aware chart colors, ensuring WCAG AAA contrast.
- **Form Display:** Chronological display of team form with opponent context, prioritizing FBref data and falling back to Understat.
- **xG Visualizations:** Enlarged Chart.js visualizations for xG/xGA trends, displaying data chronologically.

### Technical Implementations
- **Data Normalization:** Robust team name normalization for consistent data processing and logo mapping.
- **Odds Processing:** Conversion of various odds formats to implied probabilities, arbitrage detection, and optimal stake calculation.
- **API Key Management:** Robust API key rotation and retry logic for external services to ensure continuous operation.
- **On-Demand Data Loading:** Optimizes API usage by loading detailed data (e.g., Over/Under odds, betting analysis) only when requested.
- **Prediction Models:** Integrates Elo ratings (ClubElo) and market odds into a hybrid model (60% Elo, 40% Market) for balanced predictions.
- **Value Bet Identification:** Automatically flags potential value bets where the Elo model's probability significantly exceeds market probability (≥10% divergence).
- **xG Analytics:** Integrates FBref and Understat data for Expected Goals (xG), Expected Goals Against (xGA), and PPDA (Passes Per Defensive Action) metrics.
- **Dynamic Season Calculation:** Automatically determines the current football season for accurate data retrieval.

### Feature Specifications
- **Odds-Based Predictions:** Derived from real bookmaker consensus.
- **Arbitrage Detection:** Identifies arbitrage opportunities with profit margins and bookmaker details.
- **Best Odds Display:** Shows the highest available odds for each outcome.
- **Prediction Types:** Includes 1X2 (Home Win/Draw/Away Win) with probabilities and confidence scores.
- **Multi-League Support:** Covers major European leagues (Premier League, La Liga, Bundesliga, Serie A, Ligue 1) and European competitions (Champions League, Europa League).
- **Match Context:** Displays league standings, team form, Elo ratings, and xG metrics for competing teams.
- **Value Bet Identification:** Highlights matches with significant divergence between Elo and Market probabilities.

### Data Availability by Competition
- **Domestic Leagues (PL, La Liga, Bundesliga, Serie A, Ligue 1):**
  - ✅ Full support: Market odds, Elo ratings, xG metrics, team form, league standings
- **Champions League & Europa League:**
  - ✅ Supported: Market odds from 30+ bookmakers, Elo ratings (when available)
  - ❌ Limited: xG data (FBref only supports domestic leagues), league standings (Understat only tracks domestic leagues)
  - 📝 Note: Some smaller CL teams may not have Elo ratings (ClubElo focuses on major clubs)

### System Design Choices
- **Flask Application:** Core web framework for the backend.
- **Modular Structure:** Organized code for API clients, odds calculations, and the main Flask application.
- **Gunicorn:** Used for production deployment to ensure scalability.
- **Asynchronous Data Loading:** Improves initial page load times and conserves API quotas.

## External Dependencies
- **The Odds API:** Primary source for live bookmaker odds.
- **football-data.org:** API for match schedules, league standings, and team form.
- **Understat (via understat library):** Fallback for league standings and comprehensive xG metrics with caching.
- **FBref (via soccerdata):** Real Expected Goals (xG) statistics for top European leagues.
- **ClubElo.com:** Historical Elo ratings for team strength assessment.
- **luukhopman/football-logos (GitHub Repo):** Source for team logos.
- **Flask:** Python web framework.
- **gunicorn:** WSGI HTTP server.
- **requests:** HTTP library.
- **soccerdata:** Python library for football statistics.
- **understat:** Async Python library for Understat.com data.
- **aiohttp:** Async HTTP client.
- **Bootstrap 5.3:** Frontend framework.
- **Chart.js 4.4.0:** JavaScript library for data visualizations.

## Recent Updates (October 2025)

### Security Hardening (Oct 9)
- **API Key Protection:** Sanitized all logging to prevent API key exposure in URLs and error messages
- **Error Message Sanitization:** Removed all technical exception details from 7 API endpoints - users now see friendly messages like "Unable to load data. Please try again later."
- **Zero Information Leakage:** No internal errors, stack traces, or sensitive data exposed to clients

### Error Handling & User Experience (Oct 9)
- **Missing Elo Data:** Changed from alarming "❌ UNMATCHED TEAM" to informative "ℹ️ Elo rating unavailable (team not in ClubElo database)"
- **Champions League Support:** Clear messaging that xG data is unavailable for CL/EL (FBref only supports domestic leagues)
- **Graceful Degradation:** All data sources return empty data gracefully when unavailable - matches still display with available information
- **User-Friendly Messaging:** Consistent, professional error messages across all endpoints

### Code Quality & Architecture (Oct 9)
- **Centralized Configuration (`config.py`):** 85+ constants for timeouts, cache durations, model weights, betting thresholds
- **Shared Utilities (`utils.py`):** Eliminated 170+ lines of duplicate code - season calculation, team normalization, fuzzy matching
- **Zero Magic Numbers:** All hardcoded values replaced with named constants
- **Clean Imports:** Removed 8 unused packages (beautifulsoup4, selenium, etc.) - 64% reduction in dependencies
- **Modular Structure:** Single source of truth for all configuration and utility functions

### Data Availability & Documentation (Oct 9)
- **FBref League Support:** Removed CL/EL from LEAGUE_MAPPING (not supported) to avoid unnecessary API calls
- **Understat Coverage:** Clearly documented domestic-only support (PL, La Liga, Bundesliga, Serie A, Ligue 1)
- **ClubElo Limitations:** Documented that smaller teams (Pafos FC, FC Copenhagen, Union Saint-Gilloise, Qarabağ FK) aren't tracked
- **Data Availability Table:** Added clear documentation of which features work for which competitions

### Previous Updates
- **Manchester United Elo:** Fixed mapping to "Man United" (ClubElo name), Elo 1802.2 confirmed working
- **Atlético Madrid:** Added accented/unaccented versions mapping to "Atletico"  
- **Burnley Integration:** Added to logo system with #6C1D45 claret color
- **Bundesliga Logos:** Expanded with 10 teams (Wolfsburg, Stuttgart, Hoffenheim, Mainz, etc.)
- **Dark Mode WCAG AAA:** Proper semantic color overrides achieving ≥4.5:1 contrast
- **Learn Analytics Page (`/learn`):** Comprehensive guide with glossary, beginner's tutorial, curated resources, SEO meta tags

## Deployment Configuration

### Replit Autoscale Production Setup
- **Type:** Autoscale (stateless, scales to zero when idle)
- **Server:** Gunicorn WSGI - 2 workers, 120s timeout, port reuse
- **Command:** `gunicorn --bind=0.0.0.0:$PORT --workers=2 --timeout=120 --reuse-port football_predictor.app:app`
- **Port:** Uses Replit's $PORT variable (typically 8000) for health checks
- **Secrets:** 4 API keys configured (ODDS_API_KEY_1-4) with rotation
- **Cost:** $1-3/month for low traffic (auto-scales with demand)
- **Domain:** Free .replit.app subdomain, custom domain available (~$12/year)

### Production Checklist
✅ Deployment configured (Autoscale + Gunicorn)  
✅ API key rotation with 4 keys  
✅ Caching: Elo (6h), Understat (30min)  
✅ Dark mode WCAG AAA compliant  
✅ SEO meta tags on /learn page  
✅ Codebase cleaned and optimized (Oct 9, 2025)  
⏳ Update OG/Twitter image URLs after deployment  
⏳ User clicks "Deploy" to publish

## Maintenance & Optimization (October 9, 2025)

### Codebase Cleanup
- **Removed Legacy Code:** Deleted abandoned neural network approach (src/ directory with 25KB of unused code)
- **Uninstalled Unused Packages:** Removed 8 packages from old scraping approach (beautifulsoup4, selenium, selenium-wire, lxml, python-dateutil, unidecode, fake-useragent, chromedriver-autoinstaller)
- **Deleted Redundant Files:** Removed gunicorn_config.py, wsgi.py, start.sh, rapidapi_football.py (using Replit deploy config)
- **Cleaned Export Artifacts:** Removed tar.gz export, GitHub setup files, duplicate README
- **Removed Empty Directories:** Deleted models/, scraped_data/, static/ (from abandoned approaches)
- **Cleared Stale Logs:** Removed TensorFlow/CUDA errors from app.log (old neural network code)
- **Updated .gitignore:** Removed references to deleted directories, fixed uv.lock tracking

### Current Dependencies (Lean & Production-Ready)
- **Core:** flask, gunicorn, requests
- **Data Sources:** soccerdata (FBref xG), understat (async xG/standings), aiohttp
- **Total:** 8 packages (down from 22) - 64% reduction in dependencies

### Code Quality Refactoring (October 9, 2025)
- **Created config.py:** Centralized all constants for timeouts, cache durations, and model weights
  - **API Timeouts:** `API_TIMEOUT_ELO` (10s), `API_TIMEOUT_ODDS` (15s), `API_TIMEOUT_UNDERSTAT` (10s)
  - **Cache Durations:** `ELO_CACHE_DURATION_HOURS` (6h), `XG_CACHE_DURATION_HOURS` (24h), `UNDERSTAT_CACHE_DURATION_MINUTES` (30min)
  - **Model Weights:** `HYBRID_ELO_WEIGHT` (0.60), `HYBRID_MARKET_WEIGHT` (0.40)
  - **Season Calculation:** `SEASON_START_MONTH`, `SEASON_MID_MONTH`, `SEASON_END_MONTH`
  - **Betting Thresholds:** `VALUE_BET_THRESHOLD` (10%), `SAFE_BET_CONFIDENCE` (60%)
  - **85+ constants** centralized for easy tuning

- **Created utils.py:** Centralized utility functions to eliminate code duplication
  - `get_current_season()`: Dynamic season calculation for Understat/app (Aug-Dec uses current year, Jan-July uses previous)
  - `get_xg_season()`: Conservative season calculation for FBref xG (uses previous season until December for complete data)
  - `normalize_team_name()`: Team name normalization with prefix/suffix removal
  - `fuzzy_team_match()`: Fuzzy matching logic for team name matching

- **Eliminated All Magic Numbers & Duplicate Code:**
  - Updated all 5 API client modules to use centralized timeout constants
  - Updated all 3 data modules to use centralized cache duration constants
  - Removed duplicate `get_current_season()` from app.py and xg_data_fetcher.py
  - Removed hardcoded `season=2024` from understat_client.py
  - Removed duplicate `normalize_team_name()` and `fuzzy_team_match()` from app.py (70+ lines)
  - Consolidated team name mappings: `TEAM_NAME_MAP_ELO` (ClubElo) and `TEAM_NAME_MAP_FBREF` (FBref) now centralized in config.py
  - **Total reduction:** 170+ lines of duplicate code eliminated

- **Improved Maintainability:** Single source of truth for all configuration
  - All timeouts/cache durations tunable from config.py
  - Season logic updates propagate automatically across all modules
  - Team matching logic consistent across the application
  - Zero magic numbers in codebase

### Project Structure (Optimized)
```
football_predictor/
├── app.py                    # Main Flask application
├── config.py                 # ⭐ NEW: Centralized configuration constants
├── utils.py                  # ⭐ NEW: Shared utility functions
├── elo_client.py             # ClubElo integration
├── football_data_api.py      # Match schedules & standings  
├── odds_api_client.py        # Bookmaker odds (30+ sources)
├── odds_calculator.py        # Probability & arbitrage math
├── understat_client.py       # Async xG data
├── xg_data_fetcher.py        # FBref xG statistics
├── templates/
│   ├── index.html            # Main prediction interface
│   └── learn.html            # Educational SEO page
├── processed_data/xg_cache/  # FBref cache (2 leagues)
└── README.md                 # Project documentation
```

### Code Quality
✅ Zero LSP errors across all Python files  
✅ Clean imports - all packages actively used  
✅ Proper type hints and error handling  
✅ Comprehensive .gitignore (cache files only)