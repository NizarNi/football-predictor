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
The application offers odds-based predictions derived from real bookmaker consensus, arbitrage detection with profit margins and bookmaker details, and displays the best available odds for each outcome. Prediction types include 1X2 (Home Win/Draw/Away Win) with probabilities and confidence scores, Over/Under 2.5 goals, and Both Teams To Score (BTTS) with market consensus and xG-based statistical model. It supports major European leagues (Premier League, La Liga, Bundesliga, Serie A, Ligue 1) and European competitions (Champions League, Europa League). Match context includes league standings, team form, Elo ratings, xG metrics (with explicit Understat vs FBref source labels), and career xG statistics for historical perspective (last 5 seasons, fetched on-demand). Value bets are highlighted based on Elo and Market probability divergence.

### Recent Updates

#### xGA vs PSxGA Metric Separation - October 10, 2025 (Late Night)
- **Critical Distinction Implemented**: Separated defensive xGA (Expected Goals Against) from goalkeeper PSxGA (Post-Shot xG Against) metrics
  - **Understat xGA** (Season xGA): Defensive quality metric - measures all shots allowed by the defense (includes on-target, off-target, and blocked shots)
  - **FBref PSxGA** (Recent PSxGA/g): Goalkeeper quality metric - measures only on-target shots faced, considering shot placement, power, and trajectory
  - **Important**: FBref does NOT provide true defensive xGA in their keeper_adv_stats - they only provide PSxGA
- **Backend Implementation**: Updated `xg_data_fetcher.py` to correctly label FBref data as PSxGA
  - FBref's `keeper_adv_stats` PSxG field stored as both `xg_against` (legacy) and `ps_xg_against` (explicit)
  - Added `ps_xg_performance` metric (PSxG+/- per game) to measure goalkeeper shot-stopping quality
  - Clear documentation that defensive xGA comes from Understat via `/context` endpoint, not FBref
- **Frontend Labels**: Updated all FBref xGA labels to "Recent PSxGA/g (FBref)" with accurate tooltips
  - PSxGA tooltip: "Only counts on-target shots, considers shot placement, power, and trajectory. Lower = Better shot-stopping."
  - Understat xGA tooltip: "Defensive quality - all shots allowed. Lower xGA = Stronger Defense"
  - Prevents confusion between defensive quality (xGA) and goalkeeper performance (PSxGA)

#### Data Source Label Formatting - October 10, 2025 (Late Evening)
- **Line Break Implementation**: Updated all xG/xGA data source labels to display source attribution on separate lines using `<br>` tags for better visual clarity
  - Format changed from "Season xG <small>(Understat)</small>" to "Season xG<br><small>(Understat)</small>"
  - Applied to all Season xG/xGA labels (Understat source) in both grid and table views
  - Applied to all Recent xG/g and Recent xGA/g labels (FBref source) in both grid and table views
  - Prevents inline text crowding while maintaining clear data source attribution
- **Career Stats Function Call Fix**: Corrected `loadCareerStats()` to call `displayMatchContextData(contextData)` instead of non-existent `displayMatchContext()` function
  - Fixed bug preventing career stats from displaying after successful API fetch
  - Function now correctly re-renders match context with career data included

#### Tooltip & Career Stats Fixes - October 10, 2025 (Evening)
- **Tooltip Size Optimization**: Reduced Bootstrap tooltip font-size from default to 0.8rem and adjusted max-width to 300px for better on-screen readability
- **Simplified xGA Tooltip Text**: Condensed tooltip content by ~40%, using concise multi-line format with line breaks instead of verbose sentences (e.g., "23.4 xGA in 12 games\n(1.95/game avg)\n\nLeague: 1.40/game avg\nLower = Stronger 🛡️")
- **Career Stats League Code Fix**: Fixed career stats button which was sending wrong league code (EPL) to backend that expected FBref format (PL)
  - Added `mapLeagueCodeForFBref()` function to convert frontend codes (EPL, LaLiga, Bundesliga, SerieA, Ligue1) to FBref-compatible codes (PL, ESP, GER, ITA, FRA)
  - Updated `loadCareerStats()` to automatically map league codes before API requests
  - Backend now successfully loads career xG data for all supported leagues
- **BTTS Container Reset**: Created `resetBTTSButton()` function to clear BTTS predictions when switching between matches, matching behavior of Over/Under and Betting Analysis panels

#### UI Bug Fixes - October 10, 2025
- **Career Stats Button Fix**: Removed `-simple` suffix from button IDs (`home-career-btn-simple` → `home-career-btn`) so JavaScript loadCareerStats() function can find buttons correctly
- **Shortened xG Labels**: Changed labels to prevent text overlap while keeping full details in tooltips:
  - "Season Total xG (Understat)" → "Season xG <small>(Understat)</small>"
  - "Recent xG/game (FBref, last 5)" → "Recent xG/g <small>(FBref)</small>"
  - Applied consistently in both simple view and side-by-side table view
- **BTTS Display Fixes**: Fixed two frontend bugs in BTTS predictions:
  - Percentages: Multiplied decimal probabilities by 100 (now shows "45.9%" instead of "0.4%")
  - Best Odds: Correctly access nested structure `market.best_odds.yes.price` (now shows "2.10" instead of "N/A")

#### BTTS Predictions & Data Source Clarity - October 10, 2025
- **Explicit Data Source Labels**: Added clear attribution with "Season xG (Understat)" and "Recent xG/g (FBref)" labels using HTML small tags
- **xG Model Explanations**: Added detailed tooltips explaining differences between Understat (6-8 factors: shot position, angle, body part, assist type, game state, defensive pressure) and FBref (8-10 factors: shot type, location, goalkeeper position, defenders, game state, via Opta/StatsBomb data)
- **BTTS Feature Implementation**: Added Both Teams To Score predictions combining market consensus from 30+ bookmakers with xG-based statistical model
  - Backend: Created `/match/<event_id>/btts` endpoint fetching BTTS odds from The Odds API
  - Statistical Model: High BTTS probability if both xG > 1.0/game AND both xGA > 1.2/game (both teams score and face weak defenses)
  - Frontend: Added "Show BTTS Odds" button with loading states, displays Market Consensus (Yes/No probabilities with best odds) and xG Statistical Model side-by-side
  - Zero-Value Fix: Changed presence checks from truthiness to explicit `is not None` to handle valid zero xG/xGA values
- **API Optimization**: Modified `get_upcoming_matches_with_odds()` to fetch only "h2h" market for match listings, with "btts" fetched separately on-demand to avoid API 422 errors

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
