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

### Critical Fixes
- **Manchester United Elo:** Fixed mapping to "Man United" (ClubElo name), Elo 1802.2 confirmed working
- **Atlético Madrid:** Added accented/unaccented versions mapping to "Atletico"  
- **Burnley Integration:** Added to logo system with #6C1D45 claret color
- **Bundesliga Logos:** Expanded with 10 teams (Wolfsburg, Stuttgart, Hoffenheim, Mainz, etc.)
- **Dark Mode WCAG AAA:** Proper semantic color overrides achieving ≥4.5:1 contrast

### Educational Content
- **Learn Analytics Page (`/learn`):** Comprehensive guide with glossary (xG, Elo, PPDA, arbitrage, value bets), beginner's tutorial, curated resources, and SEO meta tags
- **Navigation:** Added "Learn Analytics" button to navbar (responsive design)

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
⏳ Update OG/Twitter image URLs after deployment  
⏳ User clicks "Deploy" to publish