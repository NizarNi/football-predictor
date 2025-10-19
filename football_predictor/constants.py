"""Centralized configuration constants for the Football Predictor platform."""

# ---- FotMob competition codes & IDs for the /fotmob page ----
# Stable internal codes (provider-agnostic)
FOTMOB_COMP_CODES = (
    "EPL",       # Premier League
    "LLIGA",     # LaLiga
    "SERIEA",    # Serie A
    "BUNDES",    # Bundesliga
    "LIGUE1",    # Ligue 1
    "UCL",       # UEFA Champions League
    "UEL",       # UEFA Europa League
)

# Map internal codes -> FotMob numeric competition IDs.
# TODO(codex): Confirm each ID from FotMob URLs or the fotmob-api library.
FOTMOB_COMP_IDS = {
    "EPL": 47,     # Premier League        (confirm)
    "LLIGA": 87,   # LaLiga                (confirm)
    "SERIEA": 55,  # Serie A               (confirm)
    "BUNDES": 54,  # Bundesliga            (confirm)
    "LIGUE1": 53,  # Ligue 1               (confirm)
    "UCL": 42,     # UEFA Champions League (confirm)
    "UEL": 73,     # UEFA Europa League    (confirm)
}


def is_supported_fotmob_comp(code: str) -> bool:
    """Return True if the given internal competition code is supported."""

    return code in FOTMOB_COMP_CODES


def fotmob_comp_id(code: str) -> int:
    """Return the FotMob numeric ID for a supported code; KeyError if unknown."""

    return FOTMOB_COMP_IDS[code]


# Hybrid Model Weights
HYBRID_ELO_WEIGHT = 0.60  # Elo ratings contribution to hybrid predictions
HYBRID_MARKET_WEIGHT = 0.40  # Market odds contribution to hybrid predictions

# Cache Duration
ELO_CACHE_DURATION_HOURS = 6  # ClubElo ratings cache (hours)
XG_CACHE_DURATION_HOURS = 24  # FBref xG data cache (hours)
UNDERSTAT_CACHE_DURATION_MINUTES = 30  # Understat data cache (minutes)

# API Timeouts (seconds)
API_TIMEOUT_ELO = 10  # ClubElo API timeout
API_TIMEOUT_ODDS = 15  # The Odds API timeout (needs more time for large responses)
API_TIMEOUT_UNDERSTAT = 10  # Understat async timeout
API_TIMEOUT_FOOTBALL_DATA = 15  # football-data.org timeout

# Retry Configuration
MAX_RETRIES = 5  # Maximum API retry attempts
RETRY_DELAY_BASE = 1  # Base delay between retries (seconds)
RATE_LIMIT_DELAY = 5  # Default rate limit retry delay (seconds)

# Elo Calculation Constants
ELO_DIVISOR = 400  # Standard Elo rating divisor
DRAW_PROBABILITY_BASE = 0.27  # Base draw probability
DRAW_PROBABILITY_FACTOR = 0.08  # Draw probability adjustment factor
ELO_CLOSENESS_FACTOR = 400  # Factor for close match draw probability

# Betting Thresholds
VALUE_BET_THRESHOLD = 0.10  # Minimum probability difference for value bets (10%)
HIGH_VALUE_BET_THRESHOLD = 0.15  # High value bet threshold (15%)
SAFE_BET_CONFIDENCE = 60  # Minimum confidence for safe bet classification (%)

# Default Probabilities and Lines
DEFAULT_PROBABILITY = 0.33  # Default probability for missing outcomes (33.3%)
DEFAULT_OVER_UNDER_LINE = 2.5  # Standard over/under goals line
ENHANCED_PREDICTION_LINES = [2.25, 2.5, 2.75]  # Multi-line averaging for robust predictions

# Match Data
DEFAULT_NEXT_N_DAYS = 30  # Default days ahead for match fetching
MATCH_CONTEXT_TIMEOUT = 40  # Timeout for match context loading (seconds)

# PPDA (Passes Per Defensive Action) Ratings
PPDA_EXTREME_HIGH_PRESS = 8  # < 8 PPDA: Extreme high press (Liverpool, Man City style)
PPDA_HIGH_PRESS = 12  # 8-12 PPDA: High press
PPDA_MEDIUM_PRESS = 15  # 12-15 PPDA: Medium press
PPDA_LOW_PRESS = 20  # 15-20 PPDA: Low press
# > 20 PPDA: Passive/deep defensive block

# xG Rating Thresholds
XG_EXCELLENT_ATTACK = 2.0  # Excellent attacking xG per game
XG_GOOD_ATTACK = 1.5  # Good attacking xG per game
XG_WEAK_ATTACK = 0.7  # Weak attacking xG per game

# Season Calculation (months)
SEASON_START_MONTH = 8  # August - season typically starts
SEASON_MID_MONTH = 12  # December - when to use current season data
SEASON_END_MONTH = 7  # July - season ends

# League Standings Position Thresholds
TOP_POSITION = 2  # Top 2 positions (Champions League)
EUROPEAN_POSITION = 4  # Top 4 positions (European competition)
MID_TABLE_POSITION = 10  # Mid-table cutoff
RELEGATION_ZONE_START = 18  # Start of relegation zone (for 20-team leagues)

# Word Matching (fuzzy team name matching)
MIN_WORD_LENGTH_FILTER = 2  # Minimum word length for fuzzy matching (filter out articles)
MIN_COMMON_WORDS_MATCH = 2  # Minimum common words required for match

# Flask Development Server
DEV_SERVER_HOST = "0.0.0.0"  # Bind to all interfaces
DEV_SERVER_PORT = 5000  # Standard development port

# Odds Calculation
DECIMAL_ODDS_MINIMUM = 1  # Minimum valid decimal odds
AMERICAN_ODDS_DIVISOR = 100  # Divisor for American odds conversion
ARBITRAGE_PROBABILITY_THRESHOLD = 1.0  # Total probability < 1.0 indicates arbitrage
PROFIT_MARGIN_MULTIPLIER = 100  # Convert profit margin to percentage

# API Rate Limiting
FOOTBALL_DATA_DELAY = 1  # Delay between football-data.org API calls (seconds)

# Odds API configuration
BASE_URL = "https://api.the-odds-api.com/v4"
LEAGUE_CODE_MAPPING = {
    "PL": "soccer_epl",
    "PD": "soccer_spain_la_liga",
    "BL1": "soccer_germany_bundesliga",
    "SA": "soccer_italy_serie_a",
    "FL1": "soccer_france_ligue_one",
    "CL": "soccer_uefa_champs_league",
    "EL": "soccer_uefa_europa_league"
}

# xG cache configuration
CACHE_DIR = "processed_data/xg_cache"
MATCH_LOGS_CACHE_TTL = 300  # 5 minutes in seconds
CAREER_XG_CACHE_TTL = 604800  # 7 days in seconds for historical data

# League mappings for soccerdata (FBref)
LEAGUE_MAPPING = {
    "PL": "ENG-Premier League",
    "PD": "ESP-La Liga",
    "BL1": "GER-Bundesliga",
    "SA": "ITA-Serie A",
    "FL1": "FRA-Ligue 1",
    # "CL": Not supported by FBref
    # "EL": Not supported by FBref
}

# ClubElo Team Name Mapping (Odds API names → ClubElo names)
TEAM_NAME_MAP_ELO = {
    # Premier League
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Tottenham": "Spurs",
    "Tottenham Hotspur": "Spurs",
    "Wolverhampton": "Wolves",
    "Wolverhampton Wanderers": "Wolves",
    "Brighton": "Brighton",
    "Brighton & Hove Albion": "Brighton",
    "Newcastle": "Newcastle",
    "Newcastle United": "Newcastle",
    "West Ham": "West Ham",
    "West Ham United": "West Ham",
    "Nottingham Forest": "Nott'm Forest",
    "Leicester": "Leicester",
    "Leicester City": "Leicester",

    # La Liga
    "Atletico Madrid": "Atletico",
    "Atlético Madrid": "Atletico",  # With accent
    "Athletic Bilbao": "Ath Bilbao",
    "Real Sociedad": "R Sociedad",
    "Celta Vigo": "Celta",
    "Real Betis": "Betis",

    # Bundesliga
    "Bayern Munich": "Bayern",
    "Borussia Dortmund": "Dortmund",
    "Bayer Leverkusen": "Leverkusen",
    "RB Leipzig": "RB Leipzig",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "Borussia Monchengladbach": "M'Gladbach",
    "FC Koln": "FC Koln",

    # Serie A
    "Inter Milan": "Inter",
    "AC Milan": "Milan",
    "AS Roma": "Roma",
    "Hellas Verona": "Verona",

    # Ligue 1
    "Paris Saint Germain": "Paris SG",
    "Paris St Germain": "Paris SG",
    "PSG": "Paris SG",
    "Olympique Marseille": "Marseille",
    "Olympique Lyon": "Lyon",
    "AS Monaco": "Monaco",

    # European Competitions
    "FC Porto": "Porto",
    "Sporting CP": "Sporting",
    "Benfica": "Benfica",
    "Ajax": "Ajax",
    "PSV Eindhoven": "PSV",
}

# FBref Team Name Mapping (Odds API names → FBref names)
TEAM_NAME_MAP_FBREF = {
    # Premier League
    "Manchester United": "Manchester Utd",
    "Manchester City": "Manchester City",
    "Newcastle United": "Newcastle Utd",
    "Nottingham Forest": "Nott'ham Forest",
    "Brighton": "Brighton",
    "Brighton & Hove Albion": "Brighton",
    "Tottenham": "Tottenham",
    "Tottenham Hotspur": "Tottenham",
    "West Ham": "West Ham",
    "West Ham United": "West Ham",
    "Wolves": "Wolves",
    "Wolverhampton": "Wolves",

    # La Liga
    "Athletic Club": "Athletic Club",
    "Atletico Madrid": "Atlético Madrid",
    "Real Betis": "Betis",
    "Celta Vigo": "Celta Vigo",
    "Real Sociedad": "Sociedad",
    "Deportivo Alavés": "Alavés",

    # Bundesliga
    "Bayern Munich": "Bayern Munich",
    "Bayern München": "Bayern Munich",
    "Borussia Dortmund": "Dortmund",
    "Borussia Mönchengladbach": "M'Gladbach",
    "RB Leipzig": "RB Leipzig",
    "Eintracht Frankfurt": "Eintracht Frankfurt",

    # Serie A
    "AC Milan": "Milan",
    "Inter Milan": "Inter",
    "AS Roma": "Roma",

    # Ligue 1
    "Paris Saint Germain": "Paris S-G",
    "PSG": "Paris S-G",
    "Paris Saint-Germain": "Paris S-G",
}
