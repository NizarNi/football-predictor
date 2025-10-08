#!/bin/bash

# Football Predictor Startup Script
# This script starts the Flask application using Gunicorn

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production

# Set API keys from environment or use defaults
export FOOTBALL_DATA_API_KEY_1="${FOOTBALL_DATA_API_KEY_1:-8497ba1147b44cafb94e763d4835b10f}"
export FOOTBALL_DATA_API_KEY_2="${FOOTBALL_DATA_API_KEY_2:-390cfcf491a94d4f91397e8292190407}"
export FOOTBALL_DATA_API_KEY_3="${FOOTBALL_DATA_API_KEY_3:-658f9a8caeab4ca5b9c5dd6c8a2ca393}"
export RAPIDAPI_KEY="${RAPIDAPI_KEY:-43f7ec6e98msh430d7c7e313a84dp1e03fcjsn56a36d2d62eb}"

# Change to the application directory
cd "$(dirname "$0")"

# Start Gunicorn with the configuration file
exec gunicorn --config gunicorn_config.py app:app
