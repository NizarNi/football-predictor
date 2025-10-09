# Football Prediction - Safe Bet Analyzer

## 📦 Export Package Contents

This package contains a complete football prediction platform using The Odds API with bookmaker odds-based predictions, arbitrage detection, and comprehensive xG analytics.

## 🚀 Quick Start

### Local Setup

1. **Install Python 3.8+**

2. **Install Dependencies**
```bash
cd football_predictor
pip install -r requirements.txt
```

3. **Set Environment Variables**
```bash
export ODDS_API_KEY_1="your_odds_api_key_1"
export ODDS_API_KEY_2="your_odds_api_key_2"
export ODDS_API_KEY_3="your_odds_api_key_3"
```

4. **Run the Application**
```bash
# Development mode
python app.py

# Production mode (Gunicorn)
gunicorn -c gunicorn_config.py app:app
```

5. **Open Browser**
Navigate to: `http://localhost:5000`

## 📁 Project Structure

```
football_predictor/
├── app.py                    # Main Flask application
├── odds_api_client.py        # The Odds API integration
├── odds_calculator.py        # Odds conversion & arbitrage detection
├── xg_data_fetcher.py        # FBref xG statistics
├── understat_client.py       # Understat async integration
├── elo_client.py             # ClubElo.com Elo ratings
├── templates/
│   └── index.html            # Complete responsive UI
├── requirements.txt          # Python dependencies
└── gunicorn_config.py        # Production server config
```

## 🎯 Features

### Core Functionality
- **Live Bookmaker Odds**: From 30+ international bookmakers via The Odds API
- **Consensus Predictions**: 1X2 predictions based on averaged odds probabilities
- **Arbitrage Detection**: Automatic detection of risk-free betting opportunities
- **Best Odds Display**: Shows highest available odds across all bookmakers

### Advanced Analytics
- **Hybrid Prediction Model**: 60% Elo (historical) + 40% Market (sentiment)
- **xG Analytics**: Real Expected Goals data from FBref for top 5 leagues
- **Elo Ratings**: Historical team strength from ClubElo.com (630+ teams)
- **Value Bet Detection**: Identifies when Elo and Market diverge by ≥10%
- **PPDA Pressing Metrics**: Passes Per Defensive Action intensity analysis

### UI/UX Features
- **Responsive Design**: Bootstrap 5.3 with optimized 40/60 layout
- **Dark Mode**: Complete dark theme with localStorage persistence
- **Team Logos**: Dynamic team logos from GitHub repository
- **Smart Filtering**: Bet opportunities filter (≥60%, ≥75%, ≥88% confidence)
- **On-Demand Loading**: Over/Under and xG data loaded when clicked
- **Interactive Charts**: Chart.js visualizations for xG trends
- **Comprehensive Tooltips**: Enhanced tooltips for xG, Elo, and PPDA metrics

## 🔑 API Keys Required

1. **The Odds API** (3 keys for rotation)
   - Sign up: https://the-odds-api.com/
   - Free tier: 500 requests/month
   - Set as: `ODDS_API_KEY_1`, `ODDS_API_KEY_2`, `ODDS_API_KEY_3`

## 🌍 Supported Leagues

- **Premier League** (PL)
- **La Liga** (PD)
- **Bundesliga** (BL1)
- **Serie A** (SA)
- **Ligue 1** (FL1)
- **Champions League** (CL)
- **Europa League** (EL)

## 🛠️ Technology Stack

### Backend
- **Flask**: Python web framework
- **Gunicorn**: WSGI HTTP server for production
- **The Odds API**: Live bookmaker odds (30+ bookmakers)
- **ClubElo.com**: Historical Elo ratings
- **FBref (via soccerdata)**: Real xG statistics
- **Understat**: Fallback standings with xG metrics

### Frontend
- **Bootstrap 5.3**: Responsive UI framework
- **Chart.js 4.4.0**: Interactive data visualizations
- **Vanilla JavaScript**: No framework dependencies

## 📊 Key Algorithms

### Odds-Based Predictions
```python
# Convert decimal odds to probability
probability = 1 / decimal_odds

# Normalize probabilities to sum to 1
total = home_prob + draw_prob + away_prob
normalized_home = home_prob / total
```

### Arbitrage Detection
```python
# If sum of best probabilities < 1, arbitrage exists
if (1/best_home + 1/best_draw + 1/best_away) < 1:
    profit_margin = (1 / total_probability - 1) * 100
```

### Hybrid Model (60/40)
```python
# 60% Elo (historical) + 40% Market (sentiment)
hybrid_prob = (0.6 * elo_prob) + (0.4 * market_prob)
```

### Value Bet Detection
```python
# Flag when Elo and Market diverge by ≥10%
if abs(elo_prob - market_prob) >= 0.10:
    value_bet = True
```

## 🚀 Deployment

### Replit (Recommended)
1. Import this repository to Replit
2. Set environment secrets for API keys
3. Click "Run" button
4. Use built-in deployment for production

### Heroku
```bash
# Install Heroku CLI
heroku create football-predictor
heroku config:set ODDS_API_KEY_1=your_key_1
heroku config:set ODDS_API_KEY_2=your_key_2
heroku config:set ODDS_API_KEY_3=your_key_3
git push heroku main
```

### Docker
```bash
docker build -t football-predictor .
docker run -p 5000:5000 \
  -e ODDS_API_KEY_1=your_key_1 \
  -e ODDS_API_KEY_2=your_key_2 \
  -e ODDS_API_KEY_3=your_key_3 \
  football-predictor
```

## 📝 Recent Updates

### Match Context Display Fix (Latest)
- **CSS Padding Fix**: Removed ALL table padding to prevent display shifting
- **Dynamic xG Tooltips**: Shows games played and per-game averages
- **Tooltip Initialization**: Proper disposal/reinit with requestAnimationFrame + 50ms delay

### Prediction Model Enhancement
- **1X2 Comparison Table**: Side-by-side display of Market, Elo, and Hybrid predictions
- **Divergence Indicators**: Visual indicators (⬆️/⬇️) when Elo differs from Market by ≥10%
- **Enhanced Betting Tips**: AI-powered recommendations using Hybrid Model with divergence percentages

### Form Display Enhancement
- **Opponent Context**: Shows match-by-match form with opponents (e.g., "🟩 vs ARS → 🟥 @ MCI")
- **Chronological Flow**: Oldest to newest with visual indicator for latest match
- **Home/Away Prefix**: "vs" for home games, "@" for away games

## 🤝 Contributing

This is a personal project. Feel free to fork and modify for your own use.

## ⚠️ Disclaimer

This tool is for educational and informational purposes only. Sports betting involves risk. Always gamble responsibly and within your means.

## 📄 License

MIT License - See LICENSE file for details

## 🔗 Links

- **The Odds API**: https://the-odds-api.com/
- **ClubElo**: http://clubelo.com/
- **FBref**: https://fbref.com/
- **Understat**: https://understat.com/

---

**Built with ❤️ for football analytics enthusiasts**
