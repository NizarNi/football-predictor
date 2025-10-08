"""
Lightweight odds scraper using Sports-betting bookmakers
"""

import requests
import urllib.request
import urllib.error
from bs4 import BeautifulSoup
import json
import datetime
import dateutil.parser
from typing import Dict, List, Tuple

BETCLIC_FOOTBALL_ID = "1"  # Football sport ID
WINAMAX_FOOTBALL_URL = "https://www.winamax.fr/paris-sportifs/sports/1"  # Football

def scrape_betclic_odds(league_id: str = None) -> Dict:
    """
    Scrape odds from Betclic API
    Returns dict: {"Team A - Team B": {"odds": [home, draw, away], "date": datetime, "competition": "..."}}
    """
    if not league_id:
        # Get all football competitions
        url = f"https://offer.cdn.betclic.fr/api/pub/v2/sports/{BETCLIC_FOOTBALL_ID}?application=2&countrycode=fr&language=fr&sitecode=frfr"
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            
            all_matches = {}
            for competition in data.get("competitions", []):
                comp_id = competition["id"]
                comp_matches = scrape_betclic_odds(str(comp_id))
                all_matches.update(comp_matches)
            
            return all_matches
        except:
            return {}
    
    # Get specific league
    url = f"https://offer.cdn.betclic.fr/api/pub/v2/competitions/{league_id}?application=2&countrycode=fr&fetchMultipleDefaultMarkets=true&language=fr&sitecode=frfr"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        matches_odds = {}
        if not data or "unifiedEvents" not in data:
            return matches_odds
        
        competition = data.get("name", "Unknown")
        
        for match in data["unifiedEvents"]:
            if match.get("isLive"):
                continue
            
            contestants = match.get("contestants", [])
            if not contestants or len(contestants) < 2:
                continue
            
            match_name = " - ".join([c["name"] for c in contestants])
            
            try:
                match_date = dateutil.parser.isoparse(match["date"]) + datetime.timedelta(hours=2)
            except:
                match_date = None
            
            markets = match.get("markets", [])
            if not markets:
                continue
            
            market_name = markets[0].get("name", "").strip()
            if market_name not in ["Vainqueur du match", "Résultat du match", "Vainqueur Match", "Résultat"]:
                continue
            
            odds = [selection["odds"] for selection in markets[0]["selections"]]
            
            matches_odds[match_name] = {
                "odds": odds,
                "date": match_date,
                "competition": competition,
                "bookmaker": "betclic"
            }
        
        return matches_odds
    except Exception as e:
        print(f"Error scraping Betclic: {e}")
        return {}


def scrape_winamax_odds() -> Dict:
    """
    Scrape odds from Winamax
    Returns dict: {"Team A - Team B": {"odds": [home, draw, away], "date": datetime, "competition": "..."}}
    """
    url = WINAMAX_FOOTBALL_URL
    
    try:
        req = urllib.request.Request(url)
        webpage = urllib.request.urlopen(req, timeout=10).read()
        soup = BeautifulSoup(webpage, features="lxml")
        
        matches_odds = {}
        
        for line in soup.find_all(['script']):
            if "PRELOADED_STATE" not in str(line.string):
                continue
            
            json_text = line.string.split("var PRELOADED_STATE = ")[1].split(";var BETTING_CONFIGURATION")[0]
            if json_text[-1] == ";":
                json_text = json_text[:-1]
            
            data = json.loads(json_text)
            
            if "matches" not in data:
                continue
            
            for match in data["matches"].values():
                if match.get("sportId") != 1:  # Football
                    continue
                
                if match.get("competitor1Id") == 0 or "isOutright" in match:
                    continue
                
                try:
                    match_name = match["title"].strip().replace("  ", " ")
                    match_date = datetime.datetime.fromtimestamp(match["matchStart"])
                    
                    if match_date < datetime.datetime.today():
                        continue
                    
                    main_bet_id = match["mainBetId"]
                    odds_ids = data["bets"][str(main_bet_id)]["outcomes"]
                    odds = [data["odds"][str(x)] for x in odds_ids]
                    
                    if not all(odds):
                        continue
                    
                    tournament_id = match.get("tournamentId")
                    competition = data["tournaments"].get(str(tournament_id), {}).get("tournamentName", "Unknown")
                    
                    matches_odds[match_name] = {
                        "odds": odds,
                        "date": match_date,
                        "competition": competition,
                        "bookmaker": "winamax"
                    }
                except KeyError:
                    continue
        
        return matches_odds
    except Exception as e:
        print(f"Error scraping Winamax: {e}")
        return {}


def aggregate_bookmaker_odds(match_name: str, bookmakers_data: List[Dict]) -> Tuple[List[float], float]:
    """
    Aggregate odds from multiple bookmakers for a specific match
    Returns: (averaged_odds, avg_confidence)
    """
    home_odds = []
    draw_odds = []
    away_odds = []
    
    for bookmaker_dict in bookmakers_data:
        for name, data in bookmaker_dict.items():
            if name == match_name and "odds" in data and len(data["odds"]) == 3:
                home_odds.append(data["odds"][0])
                draw_odds.append(data["odds"][1])
                away_odds.append(data["odds"][2])
    
    if not home_odds:
        return None, 0
    
    # Average the odds
    avg_home = sum(home_odds) / len(home_odds)
    avg_draw = sum(draw_odds) / len(draw_odds)
    avg_away = sum(away_odds) / len(away_odds)
    
    return [avg_home, avg_draw, avg_away], len(home_odds)


def odds_to_probabilities(odds: List[float]) -> Dict:
    """
    Convert bookmaker odds to implied probabilities
    Odds format: [home, draw, away]
    """
    if not odds or len(odds) != 3:
        return {
            "HOME_WIN": 0.33,
            "DRAW": 0.33,
            "AWAY_WIN": 0.33
        }
    
    # Calculate implied probabilities (1/odds)
    prob_home = 1 / odds[0] if odds[0] > 1 else 0
    prob_draw = 1 / odds[1] if odds[1] > 1 else 0
    prob_away = 1 / odds[2] if odds[2] > 1 else 0
    
    # Normalize to remove bookmaker margin
    total = prob_home + prob_draw + prob_away
    
    if total > 0:
        prob_home = prob_home / total
        prob_draw = prob_draw / total
        prob_away = prob_away / total
    else:
        prob_home = prob_draw = prob_away = 0.33
    
    return {
        "HOME_WIN": round(prob_home, 3),
        "DRAW": round(prob_draw, 3),
        "AWAY_WIN": round(prob_away, 3)
    }
