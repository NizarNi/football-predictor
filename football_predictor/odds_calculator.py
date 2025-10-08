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
