#!/bin/bash

# Football Predictor Startup Script
# This script starts the Flask application using Gunicorn

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production

# API keys should be set as environment variables
# FOOTBALL_DATA_API_KEY_1, FOOTBALL_DATA_API_KEY_2, FOOTBALL_DATA_API_KEY_3
# ODDS_API_KEY_1, ODDS_API_KEY_2, ODDS_API_KEY_3

# Change to the application directory
cd "$(dirname "$0")"

# Start Gunicorn with the configuration file
exec gunicorn --config gunicorn_config.py app:app
