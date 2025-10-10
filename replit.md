# Football Prediction - Safe Bet Analyzer

## Overview
A Flask-based web application providing football match predictions using real bookmaker odds. It fetches upcoming matches and live odds, converts odds to implied probabilities, detects arbitrage opportunities, and offers consensus predictions based on market data. The project aims to empower users with data-driven insights for sports betting, covering key European leagues and competitions. The business vision is to provide a robust, user-friendly platform for data-driven sports betting analysis, leveraging market potential in the growing sports analytics sector.

## User Preferences
I prefer detailed explanations. Ask before making major changes. I want iterative development. I prefer simple language.

## Recent Changes (October 2025)
### Critical Bug Fix: Pandas Boolean NA Error (October 10, 2025)
- **Issue Resolved:** Fixed "boolean value of NA is ambiguous" error that prevented match logs from loading
- **Root Cause:** Pandas Series being used in boolean conditionals (e.g., `if pd.notna(series)`) when extracting values from DataFrame rows
- **Solution:** Implemented `safe_extract_value()` helper function that checks `isinstance(value, pd.Series)` and extracts scalar with `.iloc[0]` before boolean operations
- **Performance Impact:** Eliminated 6-13 second delays per match context load (from ~26s total to ~7s for both teams)
- **Restored Features:**
  - Team form display with opponent names (e.g., "L vs Newcastle Utd"), gameweeks, and results
  - xG rolling trend charts now receive complete recent_matches data with 5-game averages (e.g., rolling xG: 0.76)
  - Match logs provide date, opponent, xG for/against, and parsed results for Chart.js visualizations
- **Technical Details:** Applied safe extraction to all row values (date, opponent, score, home_xg, away_xg) to prevent Series/scalar type inconsistencies

### Rolling xG Averages & Transparency Improvements (October 10, 2025)
- **Smart xG Calculations:** xG predictions now use rolling 5-game averages when ≥3 matches available, falling back to season averages otherwise for better recent form accuracy
- **Verified Results:** Nottingham Forest rolling xGF 0.76 (vs season 0.94), Chelsea rolling xGF 1.32 (vs season 1.56) - predictions now reflect current team performance
- **Transparency Tooltips Added:**
  - Betting Tips: "Probabilities calculated from bookmaker consensus (30+ sources via The Odds API)"
  - xG Analysis: "Uses rolling 5-game averages when available (≥3 matches), otherwise FBref 2025/26 season averages"
- **Performance:** Rolling averages calculated from match logs (now working after NA bug fix) provide more responsive predictions to recent team form changes

### Season Calculation & Dynamic Display (October 10, 2025)
- **Season Functions Fixed:** `get_current_season()` now returns END YEAR for Understat (Oct 2025 → 2026), `get_xg_season()` returns START YEAR for FBref (Oct 2025 → 2025)
- **Dynamic Season Display:** Backend sends `season_display: "2025/26"` to frontend, replacing all hardcoded "2024/25" references in tooltips
- **Documentation Updated:** Function docstrings now clarify Understat uses end-year convention (2025-26 = "2026"), FBref uses start-year convention (2025-26 = "2025")
- **Verified:** Union Berlin now shows correct 2025-26 season context (position 12, xG 9.56, form "LLWDL"), logs confirm "Fetching season 2026"

### UX & Data Accuracy Improvements
- **Team Form Display:** Improved layout with colored square emoji first (e.g., "🟩 W vs Arsenal"), chronological ordering (oldest→newest), truncated opponent names (>15 chars), reduced font size (0.85rem)
- **Dark Mode Visibility:** xG predictions and betting tips now use `var(--bs-body-color)` for proper light/dark theme contrast
- **Dynamic Tooltips:** xG/xGA Season tooltips display actual league averages from backend (e.g., "League avg: 1.47/game for La Liga 2025/26")
- **league_stats Calculation Fix:** Corrected backend to calculate per-game averages (xG/game, xGA/game) instead of totals, with zero-value teams properly included to prevent upward bias

### Multi-League Testing (October 10, 2025)
Comprehensive testing completed across all 7 supported leagues:
- **Domestic Leagues:** Premier League, La Liga (1.47 xG/game avg), Bundesliga (1.63), Serie A (1.38), Ligue 1 (1.59) - all verified with correct standings, xG/xGA/PPDA metrics, and league statistics
- **Cup Competitions:** Champions League and Europa League - graceful degradation confirmed (no standings data as expected, Elo predictions functional)

### UX Polish & Model Consistency Fixes (October 10, 2025)
- **Gameweek Display Fix:** Removed fake index-based gameweek fallbacks - now only displays actual gameweek numbers from match data, hiding GW prefix when unavailable for accuracy
- **xG Chart Chronology:** Reversed xG Trends chart X-axis to show chronological progression (oldest→newest, left→right) matching team form display order for intuitive time-series reading
- **VALUE BET Model Consistency:** Fixed betting tips to use Hybrid probabilities (60% Elo + 40% Market) instead of Market alone, now matching 1X2 prediction table calculations exactly
- **Double Chance Calculations:** Updated all Double Chance options (1X, 12, X2) to use Hybrid probabilities when Elo data available, ensuring consistency across all betting recommendations
- **Over/Under Clarity:** Added tooltip to xG-based Over 2.5 explaining it's a statistical model different from Market-based odds, clarifying the two prediction sources (xG vs Bookmaker)
- **Home Advantage Transparency:** Enhanced xG Analysis tooltip to explicitly state "Home xG × 1.15 boost, Away xG (no boost)" removing ambiguity about asymmetric calculations
- **Draw Probability Explainer:** Added tooltip to Draw row in 1X2 table explaining why probabilities vary: "Market uses bookmaker odds, Elo uses historical ratings, xG uses goal expectations - each calculates differently"
- **Loading Indicators Verified:** Confirmed progressive loading already implemented with 5 stages (Initiating → Standings → xG metrics → PPDA → Finalizing) providing step-by-step user feedback during Match Context loads

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