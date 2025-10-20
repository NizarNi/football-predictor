"""
Configuration constants for Football Prediction Platform
Centralizes all magic numbers and configuration values for maintainability
"""

USE_LEGACY_RESPONSES = True  # Toggle for global response format

import logging
import os
from logging.handlers import RotatingFileHandler

from .constants import (
    AMERICAN_ODDS_DIVISOR,
    API_TIMEOUT_ELO,
    API_TIMEOUT_FOOTBALL_DATA,
    API_TIMEOUT_ODDS,
    API_TIMEOUT_UNDERSTAT,
    ARBITRAGE_PROBABILITY_THRESHOLD,
    DECIMAL_ODDS_MINIMUM,
    DEFAULT_NEXT_N_DAYS,
    DEFAULT_OVER_UNDER_LINE,
    DEFAULT_PROBABILITY,
    DEV_SERVER_HOST,
    DEV_SERVER_PORT,
    DRAW_PROBABILITY_BASE,
    DRAW_PROBABILITY_FACTOR,
    ELO_CACHE_DURATION_HOURS,
    ELO_CLOSENESS_FACTOR,
    ELO_DIVISOR,
    ENHANCED_PREDICTION_LINES,
    EUROPEAN_POSITION,
    FOOTBALL_DATA_DELAY,
    HIGH_VALUE_BET_THRESHOLD,
    HYBRID_ELO_WEIGHT,
    HYBRID_MARKET_WEIGHT,
    MATCH_CONTEXT_TIMEOUT,
    MAX_RETRIES,
    MID_TABLE_POSITION,
    MIN_COMMON_WORDS_MATCH,
    MIN_WORD_LENGTH_FILTER,
    PPDA_EXTREME_HIGH_PRESS,
    PPDA_HIGH_PRESS,
    PPDA_LOW_PRESS,
    PPDA_MEDIUM_PRESS,
    PROFIT_MARGIN_MULTIPLIER,
    RATE_LIMIT_DELAY,
    RETRY_DELAY_BASE,
    SAFE_BET_CONFIDENCE,
    SEASON_END_MONTH,
    SEASON_MID_MONTH,
    SEASON_START_MONTH,
    TEAM_NAME_MAP_ELO,
    TOP_POSITION,
    UNDERSTAT_CACHE_DURATION_MINUTES,
    VALUE_BET_THRESHOLD,
    XG_CACHE_DURATION_HOURS,
    XG_EXCELLENT_ATTACK,
    XG_GOOD_ATTACK,
    XG_WEAK_ATTACK,
    RELEGATION_ZONE_START,
)


API_TIMEOUT = int(os.getenv("API_TIMEOUT", 10))
"""Default timeout (seconds) for outbound API calls."""

API_TIMEOUT_CONTEXT = int(os.getenv("API_TIMEOUT_CONTEXT", 8))
"""Hard timeout (seconds) for match context aggregation calls."""

API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", 3))
"""Maximum retry attempts for outbound API calls."""


def setup_logger(name: str) -> logging.Logger:
    """Create or retrieve a configured logger for the application."""

    logger = logging.getLogger(name)

    log_level_str = os.getenv("LOG_LEVEL", "DEBUG").upper()
    log_level = getattr(logging, log_level_str, logging.DEBUG)
    logger.setLevel(log_level)

    if logging.getLogger().handlers:
        logger.propagate = True
        return logger

    if not logger.handlers:
        log_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "football_predictor.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        handler.setFormatter(formatter)
        handler.setLevel(log_level)
        logger.addHandler(handler)
        logger.propagate = False

    return logger

    
