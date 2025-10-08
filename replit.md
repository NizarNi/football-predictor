# Football Prediction - Safe Bet Analyzer

## Overview
A Flask-based web application providing football match predictions using real bookmaker odds. It fetches upcoming matches and live odds from over 30 bookmakers, converts odds to implied probabilities, detects arbitrage opportunities, and offers consensus predictions based on market data. The project aims to empower users with data-driven insights for sports betting.

## Recent Changes

### Phase 2 - UI/Filter Improvements (2025-10-08) ✅
- **REDESIGNED**: Top section with centered, larger search bar (80% width, prominent position)
- **NEW FEATURE**: Unified filter bar with clean horizontal layout and centered alignment
- **NEW FEATURE**: "Bet Opportunities" dropdown filter - Very Safe (≥88%), Safe (≥75%), Moderate (≥60%), All Matches
- **INTELLIGENT**: Filter analyzes 1X2 predictions (HOME_WIN, DRAW, AWAY_WIN) to find high-confidence bets
- **MOVED**: Arbitrage checkbox integrated into unified filter bar (removed from matches section)
- **NEW FEATURE**: Dynamic filter badge showing count (e.g., "5 Very Safe Bets Found", "10 Arbitrage Opportunities")
- **ENHANCED**: Filters work cumulatively (arbitrage + confidence threshold both apply)
- **IMPROVED**: League buttons reorganized with "Browse by League:" label for better UX
- **CODE CLEANUP**: Removed old filterHtml generation, toggleArbitrageFilter function, inline filter UI
- **ARCHITECTURE**: New applyFilters() function reads current filter state from DOM and re-renders
- **HELPER FUNCTIONS**: getMaxBettingConfidence() evaluates match confidence, updateFilterBadge() manages counter display
- **FUTURE-READY**: Filter logic will automatically include Over/Under when backend pre-loads totals data

### Phase 1 - Logo System Improvements (2025-10-08) ✅
- **ENHANCED**: League-gated fuzzy team name normalization prevents cross-league collisions (Inter Miami ≠ Inter Milan, Paris FC ≠ PSG)
- **ADDED**: `fuzzyNormalizeTeamName()` function with 25+ regex patterns for common team name variations
- **IMPROVED**: League detection handles variations (Premier League/EPL/epl, La Liga/Spain/PD, etc.)
- **FIXED**: Autocomplete dropdown z-index significantly increased (parent: 10000, dropdown: 99999) for proper stacking above matches section
- **ARCHITECTURE**: Logo URL generation flow: fuzzyNormalizeTeamName → normalizeTeamNameForLogo → fallback to original name
- **SAFE**: Returns original team name if no pattern matches (graceful degradation for unknown teams/leagues)

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

### Technical Implementations
- **Team Name Normalization:** Implements `fuzzyNormalizeTeamName()` and `normalizeTeamNameForLogo()` with extensive regex patterns and mappings to handle variations and generate correct logo URLs.
- **Odds Calculation:** Converts decimal/American odds to implied probabilities, averages probabilities for consensus, detects arbitrage opportunities, and calculates optimal stake distribution.
- **API Key Rotation:** Implements robust API key rotation for both The Odds API (3 keys) and football-data.org (3 keys) to manage rate limits and ensure high availability.
- **On-Demand Data Fetching:** Features "Show Over/Under Odds" and "Betting Analysis" buttons to load data only when clicked, optimizing API quota usage.
- **Enhanced Over/Under Calculation:** Averages data from 2.25, 2.5, and 2.75 goal lines for more robust Over/Under 2.5 predictions.
- **Intelligent Betting Tips:** Provides risk-based recommendations (Safest 60-80%, Balanced 30-50%, Value 15-30%).

### Feature Specifications
- **Odds-Based Predictions:** Predictions derived from real bookmaker consensus.
- **Arbitrage Detection:** Identifies arbitrage opportunities with profit margins and displays bookmaker names/odds for each stake.
- **Best Odds Display:** Shows the highest available odds for each outcome across all bookmakers.
- **Prediction Types:** Includes 1X2 (Home Win/Draw/Away Win) with implied probabilities, confidence scores, and bookmaker count.
- **Multi-League Support:** Covers Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Champions League, and Europa League.
- **Match Context:** Displays league standings, team positions, points, and form, and generates contextual match descriptions.

### System Design Choices
- **Flask Application:** Core web framework for the backend.
- **Modular Structure:** Organized into distinct files for API clients, odds calculation, and the main Flask application.
- **Gunicorn:** Used for production deployment with multiple worker processes for scalability.
- **Asynchronous Data Loading:** Deferring loading of "Over/Under" and "Betting Analysis" data to improve initial page load times and conserve API quota.

## External Dependencies
- **The Odds API:** Primary source for live bookmaker odds from 30+ bookmakers.
- **football-data.org:** Fallback API for match schedules, league standings, and team form.
- **luukhopman/football-logos (GitHub Repo):** Source for team logos displayed in the application.
- **Flask:** Python web framework.
- **gunicorn:** WSGI HTTP server.
- **requests:** HTTP library for making API calls.
- **Bootstrap 5.3:** Frontend framework for responsive UI design.