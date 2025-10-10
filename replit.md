# Football Prediction - Safe Bet Analyzer

## Overview
This Flask-based web application provides football match predictions using real bookmaker odds. It fetches upcoming matches and live odds, converts odds to implied probabilities, detects arbitrage opportunities, and offers consensus predictions based on market data. The project aims to empower users with data-driven insights for sports betting, covering key European leagues and competitions. The business vision is to provide a robust, user-friendly platform for data-driven sports betting analysis, leveraging market potential in the growing sports analytics sector.

## User Preferences
I prefer detailed explanations. Ask before making major changes. I want iterative development. I prefer simple language.

## System Architecture

### UI/UX Decisions
The application features a responsive design using Bootstrap, optimized for desktop and mobile. Key UI elements include a prominent search bar with autocomplete, a unified filter bar, and dynamic visual cues like badges, team logos, and colored form indicators. Enhanced tooltips provide comprehensive information for metrics like xG, Elo ratings, and PPDA, with dynamic league averages calculated from real data. A complete dark mode with localStorage persistence and WCAG AAA contrast is implemented. Team form is displayed chronologically with colored square emoji first, followed by result and opponent context. xG visualizations utilize Chart.js for enlarged, chronological displays. Animated loading indicators with progress bars and educational tips enhance user experience during data fetching.

### Technical Implementations
Core technical implementations include robust team name normalization, conversion of various odds formats to implied probabilities, and arbitrage detection with optimal stake calculation. API key management incorporates rotation and retry logic. Data loading is optimized through on-demand fetching and parallel processing using `ThreadPoolExecutor`, with in-memory caching for match logs to reduce API calls. Prediction models integrate Elo ratings (ClubElo) and market odds using a hybrid approach (60% Elo, 40% Market). Value bets are identified when the Elo model's probability significantly exceeds market probability (≥10% divergence). The system integrates FBref and Understat data for Expected Goals (xG), Expected Goals Against (xGA), and PPDA metrics, dynamically determining the current football season for accurate data retrieval. Rolling 5-game xG averages are used for predictions when sufficient data is available, otherwise season averages are used.

### Feature Specifications
The application offers odds-based predictions derived from real bookmaker consensus, arbitrage detection with profit margins and bookmaker details, and displays the best available odds for each outcome. Prediction types include 1X2 (Home Win/Draw/Away Win) with probabilities and confidence scores, and Over/Under 2.5 goals. It supports major European leagues (Premier League, La Liga, Bundesliga, Serie A, Ligue 1) and European competitions (Champions League, Europa League). Match context includes league standings, team form, Elo ratings, xG metrics, and career xG statistics for historical perspective (last 5 seasons, fetched on-demand). Value bets are highlighted based on Elo and Market probability divergence.

### Recent Updates

#### Manual Career Stats Button - October 10, 2025
- **Fixed Mislabeled Tooltips**: Changed "Historical xG from FBref" to "Season 2025/26 xG" - tooltips were incorrectly labeled as "historical" when showing current season rolling averages
- **Added On-Demand Loading**: "Show Career Stats (2021-2025)" button appears below season xG stats, loads 5-year historical data only when clicked (prevents timeouts)
- **Career Stats Display**: Shows career xG/xGA averages with rich tooltips including season range (e.g., "2021/22-2025/26, 5 seasons"), comparison badges (📈 Above/📉 Below career average), and defensive performance indicators (🛡️ Better/⚠️ Worse than career for xGA)
- **User Flow**: Click match → View season stats (5-10s load) → Click "Show Career Stats" → 2-5s load → Career context displays with 5-year historical perspective
- **Error Handling**: Shows error message if fetch fails, auto-resets button after 3 seconds for retry

### System Design Choices
The core is a Flask web application with a modular structure for API clients, odds calculations, and the main application logic. Gunicorn is used for production deployment. Asynchronous data loading is implemented to improve initial page load times and conserve API quotas. A centralized `config.py` manages constants for timeouts, cache durations, model weights, and betting thresholds, while `utils.py` centralizes shared functions like season calculation and team name normalization to eliminate code duplication and improve maintainability.

## External Dependencies
- **The Odds API:** Primary source for live bookmaker odds.
- **football-data.org:** API for match schedules, league standings, and team form.
- **Understat (via `understat` library):** League standings and comprehensive xG metrics.
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