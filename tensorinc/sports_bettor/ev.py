"""Expected Value calculator — compare model predictions to sportsbook odds.

Finds +EV bets across moneylines, spreads, and totals.
"""

import logging

from tensorinc.sports_bettor.odds import american_to_decimal, american_to_implied_prob
from tensorinc.core.config import settings

log = logging.getLogger(__name__)


def calculate_ev(model_prob: float, american_odds: int | float) -> dict:
    """Calculate expected value for a bet.

    Args:
        model_prob: Our model's estimated probability of this outcome (0-1)
        american_odds: Sportsbook odds in American format

    Returns dict with:
        ev_pct: Expected value as percentage of bet
        edge: Our edge over the book (model_prob - implied_prob)
        implied_prob: Book's implied probability
        decimal_odds: Decimal odds
        kelly_fraction: Kelly criterion fraction of bankroll
    """
    decimal_odds = american_to_decimal(american_odds)
    implied_prob = american_to_implied_prob(american_odds)

    # EV = (prob_win * payout) - (prob_lose * stake)
    # Where payout = decimal_odds - 1 (profit per unit bet)
    ev = (model_prob * (decimal_odds - 1)) - ((1 - model_prob) * 1)
    ev_pct = ev * 100

    edge = model_prob - implied_prob

    # Kelly criterion: f = (bp - q) / b
    # where b = decimal_odds - 1, p = model_prob, q = 1 - model_prob
    b = decimal_odds - 1
    kelly = (b * model_prob - (1 - model_prob)) / b if b > 0 else 0
    kelly = max(kelly, 0)  # never bet negative

    return {
        "ev_pct": ev_pct,
        "edge": edge,
        "implied_prob": implied_prob,
        "decimal_odds": decimal_odds,
        "kelly_fraction": kelly,
    }


def find_moneyline_bets(prediction: dict, opportunities: list[dict],
                        game_id: str) -> list[dict]:
    """Find +EV moneyline bets for a game.

    Args:
        prediction: Model output with home_win_prob, away_win_prob
        opportunities: Normalized odds list from odds.py
        game_id: The Odds API game ID

    Returns list of bet recommendations.
    """
    bets = []
    min_ev = settings.sports_bettor_min_ev

    # Filter to this game's moneyline odds
    ml_odds = [
        o for o in opportunities
        if o["game_id"] == game_id and o["market"] == "h2h"
    ]

    for opp in ml_odds:
        name = opp["outcome_name"]
        price = opp["price"]
        home_team = opp["home_team"]
        away_team = opp["away_team"]

        # Determine which probability to use
        if name == home_team:
            model_prob = prediction["home_win_prob"]
            side = "home"
        elif name == away_team:
            model_prob = prediction["away_win_prob"]
            side = "away"
        else:
            continue

        ev_data = calculate_ev(model_prob, price)

        if ev_data["ev_pct"] >= min_ev:
            bets.append({
                "type": "moneyline",
                "game_id": game_id,
                "sport": opp["sport"],
                "home_team": home_team,
                "away_team": away_team,
                "pick": name,
                "side": side,
                "bookmaker": opp["bookmaker"],
                "american_odds": price,
                "model_prob": model_prob,
                **ev_data,
            })

    return bets


def find_spread_bets(prediction: dict, opportunities: list[dict],
                     game_id: str) -> list[dict]:
    """Find +EV spread bets for a game.

    Uses predicted spread vs book spread to estimate cover probability.
    """
    bets = []
    min_ev = settings.sports_bettor_min_ev

    spread_odds = [
        o for o in opportunities
        if o["game_id"] == game_id and o["market"] == "spreads"
    ]

    predicted_spread = prediction.get("predicted_spread", 0)

    for opp in spread_odds:
        name = opp["outcome_name"]
        price = opp["price"]
        point = opp.get("point")
        home_team = opp["home_team"]

        if point is None:
            continue

        # How much does our spread differ from the book's?
        # If we predict home -3 and book is home -7, home covering is +EV
        if name == home_team:
            # Home covers if actual_spread > -point (e.g., home -7 means home needs to win by 7+)
            # Our model predicts home_spread. Edge = predicted - book_line
            edge_points = predicted_spread - (-point)  # point is negative for favorites
        else:
            # Away covers if actual_spread < -point
            edge_points = (-point) - predicted_spread

        # Convert point edge to probability estimate
        # Rough heuristic: each point of edge ≈ 3% probability shift
        cover_prob = 0.5 + (edge_points * 0.03)
        cover_prob = max(0.01, min(0.99, cover_prob))

        ev_data = calculate_ev(cover_prob, price)

        if ev_data["ev_pct"] >= min_ev:
            bets.append({
                "type": "spread",
                "game_id": game_id,
                "sport": opp["sport"],
                "home_team": opp["home_team"],
                "away_team": opp["away_team"],
                "pick": f"{name} {point:+.1f}",
                "side": "home" if name == home_team else "away",
                "bookmaker": opp["bookmaker"],
                "american_odds": price,
                "point": point,
                "model_prob": cover_prob,
                "predicted_spread": predicted_spread,
                **ev_data,
            })

    return bets


def find_total_bets(prediction: dict, opportunities: list[dict],
                    game_id: str) -> list[dict]:
    """Find +EV over/under bets for a game.

    Uses predicted total vs book total.
    """
    bets = []
    min_ev = settings.sports_bettor_min_ev

    total_odds = [
        o for o in opportunities
        if o["game_id"] == game_id and o["market"] == "totals"
    ]

    predicted_total = prediction.get("predicted_total", 0)

    for opp in total_odds:
        name = opp["outcome_name"]  # "Over" or "Under"
        price = opp["price"]
        point = opp.get("point")

        if point is None:
            continue

        # Edge: how far off is our predicted total from the book line?
        diff = predicted_total - point

        if name == "Over":
            edge_points = diff  # positive = we think total is higher than book
        else:
            edge_points = -diff  # positive = we think total is lower than book

        # Heuristic: each point of edge ≈ 3% probability
        hit_prob = 0.5 + (edge_points * 0.03)
        hit_prob = max(0.01, min(0.99, hit_prob))

        ev_data = calculate_ev(hit_prob, price)

        if ev_data["ev_pct"] >= min_ev:
            bets.append({
                "type": "total",
                "game_id": game_id,
                "sport": opp["sport"],
                "home_team": opp["home_team"],
                "away_team": opp["away_team"],
                "pick": f"{name} {point}",
                "side": name.lower(),
                "bookmaker": opp["bookmaker"],
                "american_odds": price,
                "point": point,
                "model_prob": hit_prob,
                "predicted_total": predicted_total,
                **ev_data,
            })

    return bets


def find_all_ev_bets(prediction: dict, opportunities: list[dict],
                     game_id: str) -> list[dict]:
    """Find all +EV bets for a game across all markets.

    Returns list sorted by EV% descending, deduplicated to best book per pick.
    """
    all_bets = []
    all_bets.extend(find_moneyline_bets(prediction, opportunities, game_id))
    all_bets.extend(find_spread_bets(prediction, opportunities, game_id))
    all_bets.extend(find_total_bets(prediction, opportunities, game_id))

    # Deduplicate: keep the best odds per unique pick
    best_by_pick = {}
    for bet in all_bets:
        key = f"{bet['game_id']}_{bet['type']}_{bet['pick']}"
        if key not in best_by_pick or bet["ev_pct"] > best_by_pick[key]["ev_pct"]:
            best_by_pick[key] = bet

    result = sorted(best_by_pick.values(), key=lambda b: b["ev_pct"], reverse=True)
    return result


def format_bet(bet: dict) -> str:
    """Format a bet recommendation as a readable string."""
    odds_str = f"+{bet['american_odds']}" if bet["american_odds"] > 0 else str(bet["american_odds"])
    return (
        f"{bet['type'].upper()} | {bet['away_team']} @ {bet['home_team']}\n"
        f"  Pick: {bet['pick']} ({odds_str}) via {bet['bookmaker']}\n"
        f"  Model: {bet['model_prob']:.1%} | Book: {bet['implied_prob']:.1%} | "
        f"Edge: {bet['edge']:.1%}\n"
        f"  EV: {bet['ev_pct']:+.1f}% | Kelly: {bet['kelly_fraction']:.2%}"
    )
