# Football Prediction - Safe Bet Analyzer

## Overview
A Flask-based web application providing football match predictions using real bookmaker odds. It fetches upcoming matches and live odds, converts odds to implied probabilities, detects arbitrage opportunities, and offers consensus predictions based on market data. The project aims to empower users with data-driven insights for sports betting, covering key European leagues and competitions. The business vision is to provide a robust, user-friendly platform for data-driven sports betting analysis, leveraging market potential in the growing sports analytics sector.

## User Preferences
I prefer detailed explanations. Ask before making major changes. I want iterative development. I prefer simple language.

## Recent Changes (October 2025)
### UX & Data Accuracy Improvements
- **Team Form Display:** Improved layout with colored square emoji first (e.g., "🟩 W vs Arsenal"), content shifted left for better readability
- **Dynamic Tooltips:** xG/xGA Season tooltips now display actual league averages from backend (e.g., "League avg: 1.47/game for La Liga") instead of hardcoded values
- **league_stats Calculation Fix:** Corrected backend to calculate per-game averages (xG/game, xGA/game) instead of totals, with zero-value teams properly included to prevent upward bias

### Multi-League Testing (October 10, 2025)
Comprehensive testing completed across all 7 supported leagues:
- **Domestic Leagues:** Premier League, La Liga (1.47 xG/game avg), Bundesliga (1.63), Serie A (1.38), Ligue 1 (1.59) - all verified with correct standings, xG/xGA/PPDA metrics, and league statistics
- **Cup Competitions:** Champions League and Europa League - graceful degradation confirmed (no standings data as expected, Elo predictions functional)

## System Architecture

### UI/UX Decisions
The application features a responsive design using Bootstrap, optimized for desktop and mobile. Key UI elements include a prominent search bar with autocomplete, a unified filter bar, and dynamic visual cues like badges, team logos, and colored form indicators. Enhanced tooltips provide comprehensive information for metrics like xG, Elo ratings, and PPDA, with dynamic league averages calculated from real data. A complete dark mode with localStorage persistence and WCAG AAA contrast is implemented. Team form is displayed chronologically with colored square emoji first, followed by result and opponent context. xG visualizations utilize Chart.js for enlarged, chronological displays.

### Technical Implementations
Core technical implementations include robust team name normalization, conversion of various odds formats to implied probabilities, and arbitrage detection with optimal stake calculation. API key management incorporates rotation and retry logic for continuous operation. Data loading is optimized through on-demand fetching for detailed information. Prediction models integrate Elo ratings (ClubElo) and market odds using a hybrid approach (60% Elo, 40% Market). Value bets are identified when the Elo model's probability significantly exceeds market probability (≥10% divergence). The system also integrates FBref and Understat data for Expected Goals (xG), Expected Goals Against (xGA), and PPDA metrics, and dynamically determines the current football season for accurate data retrieval.

### Feature Specifications
The application offers odds-based predictions derived from real bookmaker consensus, arbitrage detection with profit margins and bookmaker details, and displays the best available odds for each outcome. Prediction types include 1X2 (Home Win/Draw/Away Win) with probabilities and confidence scores. It supports major European leagues (Premier League, La Liga, Bundesliga, Serie A, Ligue 1) and European competitions (Champions League, Europa League). Match context includes league standings, team form, Elo ratings, and xG metrics. Value bets are highlighted based on Elo and Market probability divergence.

### System Design Choices
The core is a Flask web application with a modular structure for API clients, odds calculations, and the main application logic. Gunicorn is used for production deployment to ensure scalability. Asynchronous data loading is implemented to improve initial page load times and conserve API quotas. A centralized `config.py` manages over 85 constants for timeouts, cache durations, model weights, and betting thresholds, while `utils.py` centralizes shared functions like season calculation and team name normalization to eliminate code duplication and improve maintainability.

## External Dependencies
- **The Odds API:** Primary source for live bookmaker odds.
- **football-data.org:** API for match schedules, league standings, and team form.
- **Understat (via `understat` library):** Fallback for league standings and comprehensive xG metrics with caching.
- **FBref (via `soccerdata`):** Real Expected Goals (xG) statistics for top European leagues.
- **ClubElo.com:** Historical Elo ratings for team strength assessment.
- **`luukhopman/football-logos` (GitHub Repo):** Source for team logos.
- **Flask:** Python web framework.
- **gunicorn:** WSGI HTTP server.
- **requests:** HTTP library.
- **soccerdata:** Python library for football statistics.
- **understat:** Async Python library for Understat.com data.
- **aiohttp:** Async HTTP client.
- **Bootstrap 5.3:** Frontend framework.
- **Chart.js 4.4.0:** JavaScript library for data visualizations.