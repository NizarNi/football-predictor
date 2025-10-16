# Football Prediction Website

A Flask-based web application that provides football match predictions using neural network models. The application fetches upcoming matches from the football-data.org API and generates predictions for match outcomes, over/under goals, and exact scores.

## Features

- **Match Predictions**: Get predictions for upcoming football matches
- **Multiple Prediction Types**:
  - 1X2 (Home Win/Draw/Away Win)
  - Over/Under goals (0.5, 1.5, 2.5, 3.5)
  - Exact score predictions
- **Confidence Levels**: Each prediction includes a confidence score
- **Multi-League Support**: Fetches matches from multiple top European leagues
- **Rate Limit Handling**: Automatic API key rotation to handle rate limits

## API Endpoints

### 1. Get Upcoming Matches with Predictions

```
GET /api/upcoming?league=<league_code>
```

**Parameters:**
- `league` (optional): League code (e.g., PL, PD, SA, BL1, FL1). If not provided, fetches from all supported leagues.

**Response:**
```json
{
  "matches": [
    {
      "match_id": 12345,
      "home_team": "Team A",
      "away_team": "Team B",
      "date": "2025-10-10T15:00:00Z",
      "competition": "Premier League",
      "predictions": {
        "1x2": {
          "prediction": "HOME_WIN",
          "confidence": 0.75,
          "probabilities": {
            "HOME_WIN": 0.75,
            "DRAW": 0.15,
            "AWAY_WIN": 0.10
          },
          "is_safe_bet": true
        },
        "over_under": {
          "2.5": {
            "prediction": "OVER",
            "confidence": 0.68,
            "probabilities": {
              "OVER": 0.68,
              "UNDER": 0.32
            },
            "is_safe_bet": false,
            "threshold": 2.5
          }
        },
        "exact_score": {
          "most_likely": "2-1",
          "confidence": 0.12,
          "is_safe_bet": false,
          "top_predictions": [
            {"score": "2-1", "probability": 0.12},
            {"score": "1-1", "probability": 0.10},
            {"score": "2-0", "probability": 0.09}
          ]
        }
      }
    }
  ]
}
```

### 2. Health Check

```
GET /
```

Returns a simple JSON response indicating the API is running.

## Legacy Endpoints

The following legacy endpoints now return **410 Gone**:

- `/match/<match_id>`
- `/predict/<match_id>`
- `/process_data`

Use `/upcoming` (and `/match/<event_id>/{xg|btts|totals}`) for current data instead.

## Installation

### Prerequisites

- Python 3.11+
- pip3
- Virtual environment (recommended)

### Setup

1. Clone or download the repository:
```bash
cd /home/ubuntu/football_predictor
```

2. Install dependencies:
```bash
pip3 install -r requirements.txt
```

3. Set up environment variables (optional):
```bash
export FOOTBALL_DATA_API_KEY_1="your_first_api_key"
export FOOTBALL_DATA_API_KEY_2="your_second_api_key"
export FOOTBALL_DATA_API_KEY_3="your_third_api_key"
```

If not set, the application will use the default API keys configured in the code.

## Running the Application

### Development Mode

For development and testing, you can run the Flask development server:

```bash
python3 app.py
```

The application will be available at `http://localhost:5000`.

### Production Mode

For production deployment, use Gunicorn:

```bash
./start.sh
```

Or manually:

```bash
gunicorn --config gunicorn_config.py app:app
```

The application will run with:
- 4 worker processes
- Listening on `0.0.0.0:5000`
- 120-second timeout
- Production-grade logging

## Configuration

### Gunicorn Configuration

The `gunicorn_config.py` file contains the Gunicorn configuration:
- **Workers**: 4 worker processes
- **Bind**: 0.0.0.0:5000
- **Timeout**: 120 seconds
- **Worker Class**: sync
- **Logging**: Info level to stdout/stderr

### API Rate Limits

The application uses three API keys and automatically rotates between them when rate limits are encountered. The football-data.org API has a limit of 10 calls per minute per key.

## Project Structure

```
football_predictor/
├── app.py                      # Main Flask application
├── football_data_api.py        # API client for football-data.org
├── neural_network_model.py     # Neural network prediction models
├── gunicorn_config.py          # Gunicorn configuration
├── start.sh                    # Startup script
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── models/                     # Trained model files (if available)
│   ├── safe_bet_1x2_model.h5
│   ├── over_under_*.h5
│   └── exact_score_model.h5
└── static/                     # Static files (if any)
```

## Models

The application uses three types of neural network models:

1. **SafeBetPredictor**: Predicts match outcomes (1X2)
2. **OverUnderPredictor**: Predicts over/under goals for different thresholds
3. **ExactScorePredictor**: Predicts exact match scores

If trained models are not available, the application will create dummy models for testing purposes.

## API Keys

The application supports multiple API keys for the football-data.org API:
- Set them as environment variables: `FOOTBALL_DATA_API_KEY_1`, `FOOTBALL_DATA_API_KEY_2`, `FOOTBALL_DATA_API_KEY_3`
- The application automatically rotates between keys when rate limits are hit
- Default keys are configured in the code but should be replaced with your own keys

## Supported Leagues

- **PL**: Premier League (England)
- **PD**: La Liga (Spain)
- **SA**: Serie A (Italy)
- **BL1**: Bundesliga (Germany)
- **FL1**: Ligue 1 (France)

## Error Handling

The application includes comprehensive error handling:
- **429 Rate Limit**: Automatic key rotation
- **403 Forbidden**: Returns error message indicating API key issues
- **500 Internal Server Error**: Returns error details for debugging

## Troubleshooting

### Models Not Loading

If the models fail to load, the application will automatically create dummy models. To use real trained models:
1. Ensure model files exist in the `models/` directory
2. Check that model files have the correct naming convention
3. Verify that all required model files (.h5, _classes.npy, _features.csv, _scaler.pkl) are present

### API Rate Limits

If you encounter rate limit errors:
1. Ensure all three API keys are valid
2. Wait for the rate limit to reset (typically 1 minute)
3. Consider adding more API keys by modifying `football_data_api.py`

### Connection Errors

If you encounter connection errors:
1. Check your internet connection
2. Verify that football-data.org is accessible
3. Check firewall settings

## License

This project is for educational and research purposes.

## Contact

For issues or questions, please contact the development team.
