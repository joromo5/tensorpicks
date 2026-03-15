"""Historical data ingestion — fetch and cache game data for model training."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from tensorpicks.core.config import settings

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
HIST_FILE = DATA_DIR / "historical_games.json"

# Free sports data APIs for historical stats
BALL_DONT_LIE_URL = "https://api.balldontlie.io/v1"  # NBA
ESPN_API_URL = "https://site.api.espn.com/apis/site/v2/sports"

# Sport-specific league mappings for ESPN API
ESPN_SPORTS = {
    "americanfootball_nfl": ("football", "nfl"),
    "americanfootball_ncaaf": ("football", "college-football"),
    "basketball_nba": ("basketball", "nba"),
    "basketball_ncaab": ("basketball", "mens-college-basketball"),
    "baseball_mlb": ("baseball", "mlb"),
    "icehockey_nhl": ("hockey", "nhl"),
    "soccer_usa_mls": ("soccer", "usa.1"),
    "soccer_epl": ("soccer", "eng.1"),
}


def _espn_get(sport: str, league: str, endpoint: str, params: dict | None = None) -> dict | None:
    """GET from ESPN public API."""
    url = f"{ESPN_API_URL}/{sport}/{league}/{endpoint}"
    try:
        resp = httpx.get(url, params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as e:
        log.warning("ESPN API error for %s/%s: %s", sport, league, e)
        return None


def fetch_espn_scoreboard(sport_key: str, dates: str | None = None) -> list[dict]:
    """Fetch scoreboard data from ESPN for a sport.

    Args:
        sport_key: Our internal sport key (e.g. americanfootball_nfl)
        dates: Date string YYYYMMDD, or None for today.

    Returns list of game dicts with teams, scores, and basic stats.
    """
    mapping = ESPN_SPORTS.get(sport_key)
    if not mapping:
        return []

    sport, league = mapping
    params = {}
    if dates:
        params["dates"] = dates

    data = _espn_get(sport, league, "scoreboard", params)
    if not data:
        return []

    games = []
    for event in data.get("events", []):
        game = _parse_espn_event(event, sport_key)
        if game:
            games.append(game)

    return games


def _parse_espn_event(event: dict, sport_key: str) -> dict | None:
    """Parse a single ESPN event into our standard game format."""
    competitions = event.get("competitions", [])
    if not competitions:
        return None

    comp = competitions[0]
    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        return None

    home = away = None
    for c in competitors:
        team_data = {
            "team_name": c.get("team", {}).get("displayName", ""),
            "team_abbr": c.get("team", {}).get("abbreviation", ""),
            "score": int(c.get("score", 0)) if c.get("score") else None,
            "is_home": c.get("homeAway") == "home",
            "record": c.get("records", [{}])[0].get("summary", "") if c.get("records") else "",
        }

        # Extract team stats if available
        stats = {}
        for stat in c.get("statistics", []):
            stats[stat.get("name", "")] = stat.get("displayValue", "")
        team_data["stats"] = stats

        if team_data["is_home"]:
            home = team_data
        else:
            away = team_data

    if not home or not away:
        return None

    # Parse venue info
    venue = comp.get("venue", {})

    game = {
        "sport": sport_key,
        "event_id": event.get("id", ""),
        "date": event.get("date", ""),
        "status": event.get("status", {}).get("type", {}).get("name", ""),
        "home_team": home["team_name"],
        "home_abbr": home["team_abbr"],
        "home_score": home["score"],
        "home_record": home["record"],
        "home_stats": home["stats"],
        "away_team": away["team_name"],
        "away_abbr": away["team_abbr"],
        "away_score": away["score"],
        "away_record": away["record"],
        "away_stats": away["stats"],
        "venue_name": venue.get("fullName", ""),
        "venue_city": venue.get("address", {}).get("city", ""),
        "venue_state": venue.get("address", {}).get("state", ""),
        "venue_indoor": venue.get("indoor", None),
    }

    return game


def fetch_espn_team_stats(sport_key: str, season: int | None = None) -> dict:
    """Fetch team-level season stats from ESPN.

    Returns dict keyed by team abbreviation with efficiency/pace stats.
    """
    mapping = ESPN_SPORTS.get(sport_key)
    if not mapping:
        return {}

    sport, league = mapping
    params = {}
    if season:
        params["season"] = season

    # Standings give us W/L records and some stats
    data = _espn_get(sport, league, "standings", params)
    if not data:
        return {}

    teams = {}
    for group in data.get("children", []):
        for entry in group.get("standings", {}).get("entries", []):
            team = entry.get("team", {})
            abbr = team.get("abbreviation", "")
            stats = {}
            for stat in entry.get("stats", []):
                stats[stat.get("name", "")] = stat.get("value", 0)
            teams[abbr] = {
                "team_name": team.get("displayName", ""),
                "abbr": abbr,
                "stats": stats,
            }

    return teams


def fetch_recent_games(sport_key: str, days: int = 30) -> list[dict]:
    """Fetch completed games from the last N days for a sport."""
    games = []
    today = datetime.now(timezone.utc)

    for i in range(days):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y%m%d")
        day_games = fetch_espn_scoreboard(sport_key, dates=date_str)
        completed = [g for g in day_games if g["status"] == "STATUS_FINAL"]
        games.extend(completed)

    log.info("Fetched %d completed games for %s (last %d days)", len(games), sport_key, days)
    return games


def fetch_team_schedule(sport_key: str, team_abbr: str) -> list[dict]:
    """Fetch a team's recent schedule to compute rest days."""
    mapping = ESPN_SPORTS.get(sport_key)
    if not mapping:
        return []

    sport, league = mapping
    # ESPN teams endpoint for schedule data
    data = _espn_get(sport, league, "teams", {"limit": 100})
    if not data:
        return []

    # Find the team ID
    team_id = None
    for team in data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
        t = team.get("team", {})
        if t.get("abbreviation", "").upper() == team_abbr.upper():
            team_id = t.get("id")
            break

    if not team_id:
        return []

    schedule = _espn_get(sport, league, f"teams/{team_id}/schedule")
    if not schedule:
        return []

    events = []
    for event in schedule.get("events", []):
        events.append({
            "date": event.get("date", ""),
            "name": event.get("name", ""),
            "status": event.get("competitions", [{}])[0]
            .get("status", {}).get("type", {}).get("name", ""),
        })

    return events


def load_historical() -> list[dict]:
    """Load cached historical games from disk."""
    if HIST_FILE.exists():
        return json.loads(HIST_FILE.read_text())
    return []


def save_historical(games: list[dict]) -> None:
    """Save historical games to disk, deduplicating by event_id."""
    existing = load_historical()
    seen_ids = {g["event_id"] for g in existing}
    new = [g for g in games if g["event_id"] not in seen_ids]

    if new:
        existing.extend(new)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        HIST_FILE.write_text(json.dumps(existing, indent=2))
        log.info("Saved %d new games (%d total)", len(new), len(existing))


def ingest_all(days: int = 90) -> list[dict]:
    """Main entry point: fetch recent games for all sports and cache them."""
    all_games = []
    for sport_key in ESPN_SPORTS:
        games = fetch_recent_games(sport_key, days=days)
        all_games.extend(games)

    save_historical(all_games)
    log.info("Ingested %d total games across all sports", len(all_games))
    return all_games
