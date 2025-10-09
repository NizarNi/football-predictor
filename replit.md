# Football Prediction - Safe Bet Analyzer

## Overview
A Flask-based web application providing football match predictions using real bookmaker odds. It fetches upcoming matches and live odds from over 30 bookmakers, converts odds to implied probabilities, detects arbitrage opportunities, and offers consensus predictions based on market data. The project aims to empower users with data-driven insights for sports betting.

## User Preferences
I prefer detailed explanations. Ask before making major changes. I want iterative development. I prefer simple language.

## System Architecture

### UI/UX Decisions
- **Responsive UI:** Utilizes Bootstrap for a responsive design.
- **Centered Search:** Large, prominent search bar at top-center (80% width) with autocomplete for team names and nicknames.
- **Unified Filter Bar:** Clean horizontal filter bar with "Bet Opportunities" dropdown and arbitrage checkbox.
- **Intelligent Filtering:** "Bet Opportunities" filter finds high-confidence bets (≥60%, ≥75%, ≥88%) across 1X2 predictions.
- **Dynamic Badges:** Shows filtered match counts (e.g., "5 Very Safe Bets Found") with auto-hiding when no filters active.
- **Team Logos:** Displays team logos from a GitHub repository on match cards and prediction views with league-gated fuzzy matching.
- **Visual Cues:** Uses colored form indicators (🟩 Win, ⬜ Draw, 🟥 Loss) and a visual 💰 ARBITRAGE badge with a green gradient border for easy identification.
- **Autocomplete Search:** Features an autocomplete search bar with team nicknames, displaying team name, matched alias, and league with an 8-result limit.
- **Popular Match Highlighting:** Highlights Champions League and Europa League fixtures with a golden badge.
- **Dark Mode:** Complete dark theme with a toggle for seamless switching, localStorage persistence, and theme-aware chart colors.

### Technical Implementations
- **Team Name Normalization:** Implements `fuzzyNormalizeTeamName()` and `normalizeTeamNameForLogo()` with extensive regex patterns and mappings to handle variations and generate correct logo URLs.
- **Odds Calculation:** Converts decimal/American odds to implied probabilities, averages probabilities for consensus, detects arbitrage opportunities, and calculates optimal stake distribution.
- **API Key Rotation:** Implements robust API key rotation for both The Odds API (3 keys) and football-data.org (3 keys) to manage rate limits and ensure high availability.
- **On-Demand Data Fetching:** Features "Show Over/Under Odds" and "Betting Analysis" buttons to load data only when clicked, optimizing API quota usage.
- **Enhanced Over/Under Calculation:** Averages data from 2.25, 2.5, and 2.75 goal lines for more robust Over/Under 2.5 predictions.
- **Intelligent Betting Tips:** Provides risk-based recommendations (Safest 60-80%, Balanced 30-50%, Value 15-30%).
- **xG Trend Visualizations:** Integrates Chart.js to display rolling 5-match xG/xGA trends with per-game data, form extraction, and clear tooltips.
- **Critical Fixes:** Includes timeout mechanisms for API calls to prevent infinite loading and ensures dark mode text visibility across the application (light backgrounds excluded from white text rule).
- **Understat Integration:** Async-based fallback for standings with 30-minute caching, 10-second timeouts, and aggregated xG metrics (total xG, xGA, PPDA coefficients).

### Feature Specifications
- **Odds-Based Predictions:** Predictions derived from real bookmaker consensus.
- **Arbitrage Detection:** Identifies arbitrage opportunities with profit margins and displays bookmaker names/odds for each stake.
- **Best Odds Display:** Shows the highest available odds for each outcome across all bookmakers.
- **Prediction Types:** Includes 1X2 (Home Win/Draw/Away Win) with implied probabilities, confidence scores, and bookmaker count.
- **Multi-League Support:** Covers Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Champions League, and Europa League.
- **Match Context:** Displays league standings, team positions, points, form, and xG metrics (xGF, xGA, overperformance) for both teams.
- **xG Analytics:** Real Expected Goals data from FBref showing team attacking/defensive strength, xG-based match predictions, and Over/Under 2.5 recommendations (available for top 5 leagues only).

### System Design Choices
- **Flask Application:** Core web framework for the backend.
- **Modular Structure:** Organized into distinct files for API clients, odds calculation, and the main Flask application.
- **Gunicorn:** Used for production deployment with multiple worker processes for scalability.
- **Asynchronous Data Loading:** Deferring loading of "Over/Under" and "Betting Analysis" data to improve initial page load times and conserve API quota.

## External Dependencies
- **The Odds API:** Primary source for live bookmaker odds from 30+ bookmakers.
- **football-data.org:** API for match schedules, league standings, and team form (primary source, occasional SSL/500 errors).
- **Understat (via understat library):** Fallback source for league standings with comprehensive xG metrics (PL, La Liga, Bundesliga, Serie A, Ligue 1). Includes 30-minute caching to optimize performance.
- **FBref (via soccerdata):** Real Expected Goals (xG) statistics from FBref.com for top 5 European leagues.
- **luukhopman/football-logos (GitHub Repo):** Source for team logos displayed in the application.
- **Flask:** Python web framework.
- **gunicorn:** WSGI HTTP server.
- **requests:** HTTP library for making API calls.
- **soccerdata:** Python library for fetching football statistics from various sources including FBref.
- **understat:** Async Python library for Understat.com data (team stats, match results, win probabilities).
- **aiohttp:** Async HTTP client for Understat integration.
- **Bootstrap 5.3:** Frontend framework for responsive UI design.
- **Chart.js 4.4.0:** JavaScript library for interactive data visualizations.