import logging

from config import DEFAULT_PROBABILITY
from utils import fuzzy_team_match, normalize_team_name


logger = logging.getLogger(__name__)

def decimal_to_probability(decimal_odds):
    if decimal_odds <= 1:
        return 0
    return 1 / decimal_odds

def american_to_probability(american_odds):
    if american_odds > 0:
        return 100 / (american_odds + 100)
    else:
        return abs(american_odds) / (abs(american_odds) + 100)


def _identify_outcome_side(outcome_name, home_team, away_team):
    if not outcome_name:
        return None

    name_lower = outcome_name.lower()
    if name_lower == 'draw':
        return 'draw'

    def _matches(candidate):
        return bool(candidate) and (
            normalize_team_name(outcome_name) == normalize_team_name(candidate)
            or fuzzy_team_match(outcome_name, candidate)
        )

    if _matches(home_team):
        return 'home'
    if _matches(away_team):
        return 'away'

    return None


def calculate_averaged_probabilities(bookmakers, home_team, away_team):
    home_probs = []
    draw_probs = []
    away_probs = []

    for bookmaker in bookmakers:
        for market in bookmaker.get('markets', []):
            if market['key'] == 'h2h':
                outcomes = market.get('outcomes', [])

                for outcome in outcomes:
                    prob = decimal_to_probability(outcome['price'])
                    side = _identify_outcome_side(outcome.get('name'), home_team, away_team)

                    if side == 'home':
                        home_probs.append(prob)
                    elif side == 'draw':
                        draw_probs.append(prob)
                    elif side == 'away':
                        away_probs.append(prob)
                    else:
                        logger.debug(
                            "Unmatched outcome '%s' for fixture %s vs %s",
                            outcome.get('name'),
                            home_team,
                            away_team,
                        )

    avg_home = sum(home_probs) / len(home_probs) if home_probs else DEFAULT_PROBABILITY
    avg_draw = sum(draw_probs) / len(draw_probs) if draw_probs else DEFAULT_PROBABILITY
    avg_away = sum(away_probs) / len(away_probs) if away_probs else DEFAULT_PROBABILITY

    total = avg_home + avg_draw + avg_away
    if total > 0:
        avg_home /= total
        avg_draw /= total
        avg_away /= total

    return {
        "HOME_WIN": round(avg_home, 4),
        "DRAW": round(avg_draw, 4),
        "AWAY_WIN": round(avg_away, 4)
    }

def extract_best_odds(bookmakers, home_team, away_team):
    best_home_odds = {"price": 0, "bookmaker": None}
    best_draw_odds = {"price": 0, "bookmaker": None}
    best_away_odds = {"price": 0, "bookmaker": None}

    for bookmaker in bookmakers:
        for market in bookmaker.get('markets', []):
            if market['key'] == 'h2h':
                for outcome in market.get('outcomes', []):
                    price = outcome['price']
                    side = _identify_outcome_side(outcome.get('name'), home_team, away_team)

                    if side == 'home':
                        if price > best_home_odds["price"]:
                            best_home_odds = {"price": price, "bookmaker": bookmaker['title']}
                    elif side == 'draw':
                        if price > best_draw_odds["price"]:
                            best_draw_odds = {"price": price, "bookmaker": bookmaker['title']}
                    elif side == 'away':
                        if price > best_away_odds["price"]:
                            best_away_odds = {"price": price, "bookmaker": bookmaker['title']}

    return {
        "home": best_home_odds,
        "draw": best_draw_odds,
        "away": best_away_odds
    }

def detect_arbitrage(bookmakers, home_team, away_team):
    best_odds = extract_best_odds(bookmakers, home_team, away_team)
    
    if not all([best_odds["home"]["price"], best_odds["draw"]["price"], best_odds["away"]["price"]]):
        return None
    
    prob_home = decimal_to_probability(best_odds["home"]["price"])
    prob_draw = decimal_to_probability(best_odds["draw"]["price"])
    prob_away = decimal_to_probability(best_odds["away"]["price"])
    
    total_prob = prob_home + prob_draw + prob_away
    
    if total_prob < 1.0:
        profit_margin = (1 / total_prob - 1) * 100
        return {
            "is_arbitrage": True,
            "profit_margin": round(profit_margin, 2),
            "total_probability": round(total_prob, 4),
            "best_odds": best_odds,
            "stakes": {
                "home": round(prob_home / total_prob * 100, 2),
                "draw": round(prob_draw / total_prob * 100, 2),
                "away": round(prob_away / total_prob * 100, 2)
            }
        }
    
    return None

def calculate_totals_from_odds(odds_data):
    """Calculate over/under probabilities from totals market"""
    bookmakers = odds_data.get('bookmakers', [])
    
    if not bookmakers:
        return {
            "predictions": [],
            "bookmaker_count": 0
        }
    
    totals_by_line = {}
    
    for bookmaker in bookmakers:
        for market in bookmaker.get('markets', []):
            if market['key'] == 'totals':
                outcomes = market.get('outcomes', [])
                
                for outcome in outcomes:
                    line = outcome.get('point', 2.5)
                    name = outcome['name']
                    price = outcome['price']
                    prob = decimal_to_probability(price)
                    
                    if line not in totals_by_line:
                        totals_by_line[line] = {'over': [], 'under': [], 'over_odds': [], 'under_odds': []}
                    
                    if name.lower() == 'over':
                        totals_by_line[line]['over'].append(prob)
                        totals_by_line[line]['over_odds'].append({'price': price, 'bookmaker': bookmaker['title']})
                    elif name.lower() == 'under':
                        totals_by_line[line]['under'].append(prob)
                        totals_by_line[line]['under_odds'].append({'price': price, 'bookmaker': bookmaker['title']})
    
    predictions = []
    common_lines = [1.5, 2.5, 3.5]
    
    # Special handling for 2.5: combine with 2.25 and 2.75 for enhanced prediction
    if 2.5 in totals_by_line or 2.25 in totals_by_line or 2.75 in totals_by_line:
        combined_over = []
        combined_under = []
        combined_over_odds = []
        combined_under_odds = []
        lines_used = []
        
        for adjacent_line in [2.25, 2.5, 2.75]:
            if adjacent_line in totals_by_line:
                lines_used.append(adjacent_line)
                combined_over.extend(totals_by_line[adjacent_line]['over'])
                combined_under.extend(totals_by_line[adjacent_line]['under'])
                combined_over_odds.extend(totals_by_line[adjacent_line]['over_odds'])
                combined_under_odds.extend(totals_by_line[adjacent_line]['under_odds'])
        
        if combined_over and combined_under:
            avg_over = sum(combined_over) / len(combined_over)
            avg_under = sum(combined_under) / len(combined_under)
            
            total = avg_over + avg_under
            if total > 0:
                avg_over /= total
                avg_under /= total
            
            best_over = max(combined_over_odds, key=lambda x: x['price']) if combined_over_odds else None
            best_under = max(combined_under_odds, key=lambda x: x['price']) if combined_under_odds else None
            
            predictions.append({
                "line": 2.5,
                "probabilities": {
                    "over": round(avg_over, 4),
                    "under": round(avg_under, 4)
                },
                "prediction": "OVER" if avg_over > avg_under else "UNDER",
                "confidence": round(max(avg_over, avg_under) * 100, 1),
                "best_odds": {
                    "over": best_over,
                    "under": best_under
                },
                "bookmaker_count": max(len(combined_over), len(combined_under)),
                "enhanced": len(lines_used) > 1,
                "lines_used": lines_used
            })
    
    # Handle 1.5 and 3.5 normally
    for line in [1.5, 3.5]:
        if line in totals_by_line:
            data = totals_by_line[line]
            if data['over'] and data['under']:
                avg_over = sum(data['over']) / len(data['over'])
                avg_under = sum(data['under']) / len(data['under'])
                
                total = avg_over + avg_under
                if total > 0:
                    avg_over /= total
                    avg_under /= total
                
                best_over = max(data['over_odds'], key=lambda x: x['price']) if data['over_odds'] else None
                best_under = max(data['under_odds'], key=lambda x: x['price']) if data['under_odds'] else None
                
                predictions.append({
                    "line": line,
                    "probabilities": {
                        "over": round(avg_over, 4),
                        "under": round(avg_under, 4)
                    },
                    "prediction": "OVER" if avg_over > avg_under else "UNDER",
                    "confidence": round(max(avg_over, avg_under) * 100, 1),
                    "best_odds": {
                        "over": best_over,
                        "under": best_under
                    },
                    "bookmaker_count": max(len(data['over']), len(data['under']))
                })
    
    return {
        "predictions": predictions,
        "bookmaker_count": len(bookmakers)
    }

def calculate_btts_probability_from_xg(home_xg_per_game, away_xg_per_game, home_xga_per_game, away_xga_per_game):
    """
    Calculate BTTS probability based on xG/xGA stats.
    
    Logic:
    - High probability (>65%): Both teams xG > 1.0/game AND both face weak defenses (xGA > 1.2/game)
    - Medium probability (45-65%): One team has strong attack (xG > 1.0) and other has weak defense  
    - Low probability (<45%): Both have low scoring rates or face strong defenses
    
    Args:
        home_xg_per_game: Home team's expected goals per game
        away_xg_per_game: Away team's expected goals per game
        home_xga_per_game: Home team's expected goals against per game (what they concede)
        away_xga_per_game: Away team's expected goals against per game (what they concede)
    
    Returns:
        dict with yes_probability, no_probability, confidence, reasoning
    """
    # Convert to float and handle None values
    home_xg = float(home_xg_per_game) if home_xg_per_game else 0.0
    away_xg = float(away_xg_per_game) if away_xg_per_game else 0.0
    home_xga = float(home_xga_per_game) if home_xga_per_game else 1.0
    away_xga = float(away_xga_per_game) if away_xga_per_game else 1.0
    
    # Calculate scoring probability for each team
    # Home team scores if: home_xg > threshold AND away_xga > threshold (weak defense)
    # Away team scores if: away_xg > threshold AND home_xga > threshold (weak defense)
    
    home_likely_to_score = home_xg > 1.0 and away_xga > 1.2
    away_likely_to_score = away_xg > 1.0 and home_xga > 1.2
    
    # Calculate base BTTS probability
    if home_likely_to_score and away_likely_to_score:
        # Both teams have strong attack AND face weak defenses
        btts_yes = 0.70  # High probability
        reasoning = f"Both teams attacking well: {home_xg:.1f} xG/game (home) vs {away_xg:.1f} xG/game (away), both facing vulnerable defenses ({away_xga:.1f} xGA, {home_xga:.1f} xGA)"
    elif home_likely_to_score or away_likely_to_score:
        # Only one team has strong attack/weak defense combo
        btts_yes = 0.55  # Medium-high probability
        if home_likely_to_score:
            reasoning = f"Home team attacking strongly ({home_xg:.1f} xG/game) vs weak defense ({away_xga:.1f} xGA), but away team may struggle to score ({away_xg:.1f} xG/game)"
        else:
            reasoning = f"Away team attacking strongly ({away_xg:.1f} xG/game) vs weak defense ({home_xga:.1f} xGA), but home team may struggle to score ({home_xg:.1f} xG/game)"
    else:
        # Neither team has strong attack/weak defense combo
        # But still calculate based on general scoring rates
        avg_scoring_rate = (home_xg + away_xg) / 2.0
        
        if avg_scoring_rate > 1.5:
            btts_yes = 0.50  # Medium probability - both teams create some chances
            reasoning = f"Moderate attacking threat from both teams (avg {avg_scoring_rate:.1f} xG/game), decent chance both score"
        elif avg_scoring_rate > 1.0:
            btts_yes = 0.40  # Low-medium probability
            reasoning = f"Limited attacking threat (avg {avg_scoring_rate:.1f} xG/game), low chance both teams score"
        else:
            btts_yes = 0.30  # Low probability
            reasoning = f"Weak attacking teams (avg {avg_scoring_rate:.1f} xG/game), unlikely both score"
    
    # Fine-tune based on defensive vulnerability
    defense_factor = (home_xga + away_xga) / 2.0
    if defense_factor > 1.5:
        btts_yes += 0.05  # Both defenses leaky - boost BTTS probability
    elif defense_factor < 0.9:
        btts_yes -= 0.05  # Both defenses strong - reduce BTTS probability
    
    # Ensure probability stays in valid range
    btts_yes = max(0.0, min(1.0, btts_yes))
    btts_no = 1.0 - btts_yes
    
    return {
        "yes_probability": round(btts_yes, 4),
        "no_probability": round(btts_no, 4),
        "prediction": "YES" if btts_yes > btts_no else "NO",
        "confidence": round(max(btts_yes, btts_no) * 100, 1),
        "reasoning": reasoning,
        "xg_data": {
            "home_xg": home_xg,
            "away_xg": away_xg,
            "home_xga": home_xga,
            "away_xga": away_xga
        }
    }

def calculate_btts_from_odds(odds_data):
    """Calculate Both Teams To Score probabilities from btts market"""
    bookmakers = odds_data.get('bookmakers', [])
    
    if not bookmakers:
        return {
            "yes_probability": 0.5,
            "no_probability": 0.5,
            "bookmaker_count": 0,
            "best_odds": {"yes": None, "no": None}
        }
    
    yes_probs = []
    no_probs = []
    yes_odds = []
    no_odds = []
    
    for bookmaker in bookmakers:
        for market in bookmaker.get('markets', []):
            if market['key'] == 'btts':
                outcomes = market.get('outcomes', [])
                
                for outcome in outcomes:
                    price = outcome['price']
                    name = outcome['name'].lower()
                    prob = decimal_to_probability(price)
                    
                    if name == 'yes':
                        yes_probs.append(prob)
                        yes_odds.append({'price': price, 'bookmaker': bookmaker['title']})
                    elif name == 'no':
                        no_probs.append(prob)
                        no_odds.append({'price': price, 'bookmaker': bookmaker['title']})
    
    if yes_probs and no_probs:
        avg_yes = sum(yes_probs) / len(yes_probs)
        avg_no = sum(no_probs) / len(no_probs)
        
        # Normalize
        total = avg_yes + avg_no
        if total > 0:
            avg_yes /= total
            avg_no /= total
        
        best_yes = max(yes_odds, key=lambda x: x['price']) if yes_odds else None
        best_no = max(no_odds, key=lambda x: x['price']) if no_odds else None
        
        return {
            "yes_probability": round(avg_yes, 4),
            "no_probability": round(avg_no, 4),
            "prediction": "YES" if avg_yes > avg_no else "NO",
            "confidence": round(max(avg_yes, avg_no) * 100, 1),
            "best_odds": {
                "yes": best_yes,
                "no": best_no
            },
            "bookmaker_count": max(len(yes_probs), len(no_probs))
        }
    
    return {
        "yes_probability": 0.5,
        "no_probability": 0.5,
        "bookmaker_count": 0,
        "best_odds": {"yes": None, "no": None}
    }

def calculate_predictions_from_odds(match_data):
    bookmakers = match_data.get('bookmakers', [])
    home_team = match_data.get('home_team', '')
    away_team = match_data.get('away_team', '')
    
    if not bookmakers:
        return {
            "probabilities": {
                "HOME_WIN": 0.33,
                "DRAW": 0.33,
                "AWAY_WIN": 0.33
            },
            "prediction": "N/A",
            "confidence": 0,
            "bookmaker_count": 0,
            "best_odds": None,
            "arbitrage": None
        }
    
    probabilities = calculate_averaged_probabilities(bookmakers, home_team, away_team)
    best_odds = extract_best_odds(bookmakers, home_team, away_team)
    arbitrage = detect_arbitrage(bookmakers, home_team, away_team)
    
    max_prob = max(probabilities.values())
    if probabilities["HOME_WIN"] == max_prob:
        prediction = "HOME_WIN"
    elif probabilities["DRAW"] == max_prob:
        prediction = "DRAW"
    else:
        prediction = "AWAY_WIN"
    
    confidence = round(max_prob * 100, 1)
    
    return {
        "probabilities": probabilities,
        "prediction": prediction,
        "confidence": confidence,
        "bookmaker_count": len(bookmakers),
        "best_odds": best_odds,
        "arbitrage": arbitrage
    }
