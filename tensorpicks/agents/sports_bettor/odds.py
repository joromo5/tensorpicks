"""The Odds API client — fetch live odds for spreads, totals, moneylines, and player props."""

import logging
from datetime import datetime, timezone

import httpx

from tensorpicks.core.config import settings

log = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com"

# Major sports we track
SPORTS = [
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "basketball_nba",
    "basketball_ncaab",
    "baseball_mlb",
    "icehockey_nhl",
    "soccer_usa_mls",
    "soccer_epl",
]

# Markets we pull
MARKETS = ["h2h", "spreads", "totals"]

# Regions for odds
REGIONS = "us"


def _get(path: str, params: dict | None = None) -> dict | list | None:
    """Make authenticated GET to The Odds API."""
    if not settings.the_odds_api_key:
        log.error("THE_ODDS_API_KEY not set")
        return None
    params = params or {}
    params["apiKey"] = settings.the_odds_api_key
    try:
        resp = httpx.get(f"{BASE_URL}{path}", params=params, timeout=30)
        resp.raise_for_status()
        remaining = resp.headers.get("x-requests-remaining", "?")
        log.info("Odds API requests remaining: %s", remaining)
        return resp.json()
    except httpx.HTTPError as e:
        log.error("Odds API request failed: %s", e)
        return None


def get_active_sports() -> list[dict]:
    """Return list of in-season sports available on the API."""
    data = _get("/v4/sports")
    if not data:
        return []
    return [s for s in data if s.get("active") and s["key"] in SPORTS]


def get_odds(sport: str, markets: list[str] | None = None) -> list[dict]:
    """Fetch upcoming game odds for a sport.

    Returns list of game dicts, each with bookmaker odds for requested markets.
    """
    mkts = ",".join(markets or MARKETS)
    data = _get(f"/v4/sports/{sport}/odds", {
        "regions": REGIONS,
        "markets": mkts,
        "oddsFormat": "american",
    })
    return data or []


def get_scores(sport: str, days_from: int = 3) -> list[dict]:
    """Fetch recent scores/results for a sport (for settling bets)."""
    data = _get(f"/v4/sports/{sport}/scores", {
        "daysFrom": days_from,
    })
    return data or []


def get_events(sport: str) -> list[dict]:
    """Fetch upcoming events for a sport."""
    data = _get(f"/v4/sports/{sport}/events")
    return data or []


def get_player_props(sport: str, event_id: str, prop_markets: list[str] | None = None) -> dict:
    """Fetch player prop odds for a specific event.

    Common prop markets: player_points, player_rebounds, player_assists,
    player_pass_tds, player_rush_yds, player_recv_yds, etc.
    """
    mkts = prop_markets or [
        "player_points", "player_rebounds", "player_assists",
        "player_pass_tds", "player_rush_yds", "player_recv_yds",
        "player_hits", "player_strikeouts",
    ]
    data = _get(f"/v4/sports/{sport}/events/{event_id}/odds", {
        "regions": REGIONS,
        "markets": ",".join(mkts),
        "oddsFormat": "american",
    })
    return data or {}


def normalize_odds(games: list[dict]) -> list[dict]:
    """Flatten raw API response into a clean list of betting opportunities.

    Each opportunity is a dict with:
        sport, game_id, commence_time, home_team, away_team,
        market, bookmaker, outcome_name, price (american odds), point (spread/total)
    """
    opportunities = []
    for game in games:
        base = {
            "sport": game.get("sport_key", ""),
            "game_id": game.get("id", ""),
            "commence_time": game.get("commence_time", ""),
            "home_team": game.get("home_team", ""),
            "away_team": game.get("away_team", ""),
        }

        for book in game.get("bookmakers", []):
            bookmaker = book["key"]
            for market in book.get("markets", []):
                market_key = market["key"]
                for outcome in market.get("outcomes", []):
                    opp = {
                        **base,
                        "market": market_key,
                        "bookmaker": bookmaker,
                        "outcome_name": outcome.get("name", ""),
                        "price": outcome.get("price", 0),
                        "point": outcome.get("point"),
                    }
                    opportunities.append(opp)

    return opportunities


def american_to_decimal(american: int | float) -> float:
    """Convert American odds to decimal odds."""
    if american > 0:
        return (american / 100) + 1
    return (100 / abs(american)) + 1


def american_to_implied_prob(american: int | float) -> float:
    """Convert American odds to implied probability (no-vig)."""
    if american < 0:
        return abs(american) / (abs(american) + 100)
    return 100 / (american + 100)


def get_consensus_odds(opportunities: list[dict], game_id: str, market: str,
                       outcome_name: str) -> dict:
    """Get average / best odds across books for a specific outcome."""
    matching = [
        o for o in opportunities
        if o["game_id"] == game_id
        and o["market"] == market
        and o["outcome_name"] == outcome_name
    ]
    if not matching:
        return {}

    prices = [o["price"] for o in matching]
    best_price = max(prices) if prices[0] > 0 else max(prices)
    avg_price = sum(prices) / len(prices)
    points = [o["point"] for o in matching if o.get("point") is not None]
    avg_point = sum(points) / len(points) if points else None

    return {
        "best_price": best_price,
        "avg_price": avg_price,
        "avg_point": avg_point,
        "num_books": len(matching),
        "best_book": next(o["bookmaker"] for o in matching if o["price"] == best_price),
    }


def fetch_all_upcoming() -> list[dict]:
    """Fetch and normalize odds across all tracked sports. Main entry point."""
    all_opps = []
    active = get_active_sports()
    log.info("Fetching odds for %d active sports", len(active))

    for sport in active:
        key = sport["key"]
        games = get_odds(key)
        if games:
            opps = normalize_odds(games)
            all_opps.extend(opps)
            log.info("  %s: %d games, %d opportunities", key, len(games), len(opps))

    log.info("Total betting opportunities: %d", len(all_opps))
    return all_opps
