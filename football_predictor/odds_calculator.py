def decimal_to_probability(decimal_odds):
    if decimal_odds <= 1:
        return 0
    return 1 / decimal_odds

def american_to_probability(american_odds):
    if american_odds > 0:
        return 100 / (american_odds + 100)
    else:
        return abs(american_odds) / (abs(american_odds) + 100)

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
                    name = outcome['name']
                    
                    if name == home_team:
                        home_probs.append(prob)
                    elif name.lower() == 'draw':
                        draw_probs.append(prob)
                    elif name == away_team:
                        away_probs.append(prob)
    
    avg_home = sum(home_probs) / len(home_probs) if home_probs else 0.33
    avg_draw = sum(draw_probs) / len(draw_probs) if draw_probs else 0.33
    avg_away = sum(away_probs) / len(away_probs) if away_probs else 0.33
    
    total = avg_home + avg_draw + avg_away
    if total > 0:
        avg_home /= total
        avg_draw /= total
        avg_away /= total
    
    return {
        "home_win": round(avg_home, 4),
        "draw": round(avg_draw, 4),
        "away_win": round(avg_away, 4)
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
                    name = outcome['name']
                    
                    if name == home_team:
                        if price > best_home_odds["price"]:
                            best_home_odds = {"price": price, "bookmaker": bookmaker['title']}
                    elif name.lower() == 'draw':
                        if price > best_draw_odds["price"]:
                            best_draw_odds = {"price": price, "bookmaker": bookmaker['title']}
                    elif name == away_team:
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

def calculate_predictions_from_odds(match_data):
    bookmakers = match_data.get('bookmakers', [])
    home_team = match_data.get('home_team', '')
    away_team = match_data.get('away_team', '')
    
    if not bookmakers:
        return {
            "probabilities": {
                "home_win": 0.33,
                "draw": 0.33,
                "away_win": 0.33
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
    if probabilities["home_win"] == max_prob:
        prediction = "HOME_WIN"
    elif probabilities["draw"] == max_prob:
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
