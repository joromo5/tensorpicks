"""Feature engineering — build ML features from game data.

Features include: home/away, weather, rest days, pace, efficiency ratings,
win streaks, head-to-head, and more.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
import numpy as np

from tensorinc.core.config import settings

log = logging.getLogger(__name__)

# Sports played outdoors (weather matters)
OUTDOOR_SPORTS = {
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "baseball_mlb",
    "soccer_usa_mls",
    "soccer_epl",
}


def build_features(game: dict, historical: list[dict], team_stats: dict) -> dict | None:
    """Build a full feature vector for a game.

    Args:
        game: Current game dict (from data_ingest)
        historical: List of past completed games
        team_stats: Dict of team-level season stats keyed by abbreviation

    Returns feature dict or None if insufficient data.
    """
    sport = game.get("sport", "")
    home = game.get("home_abbr", "")
    away = game.get("away_abbr", "")
    game_date = _parse_date(game.get("date", ""))

    if not home or not away or not game_date:
        return None

    # Filter historical to this sport
    sport_history = [g for g in historical if g.get("sport") == sport]

    features = {}

    # 1. Home/away indicator (always 1 = home perspective)
    features["is_home"] = 1

    # 2. Win/loss records
    home_record = _parse_record(game.get("home_record", ""))
    away_record = _parse_record(game.get("away_record", ""))
    features["home_win_pct"] = home_record["win_pct"]
    features["away_win_pct"] = away_record["win_pct"]
    features["home_wins"] = home_record["wins"]
    features["home_losses"] = home_record["losses"]
    features["away_wins"] = away_record["wins"]
    features["away_losses"] = away_record["losses"]

    # 3. Rest days
    features["home_rest_days"] = _days_since_last_game(home, game_date, sport_history)
    features["away_rest_days"] = _days_since_last_game(away, game_date, sport_history)
    features["rest_advantage"] = features["home_rest_days"] - features["away_rest_days"]

    # 4. Recent form (last 5 and last 10 games)
    features["home_last5_win_pct"] = _recent_win_pct(home, game_date, sport_history, n=5)
    features["home_last10_win_pct"] = _recent_win_pct(home, game_date, sport_history, n=10)
    features["away_last5_win_pct"] = _recent_win_pct(away, game_date, sport_history, n=5)
    features["away_last10_win_pct"] = _recent_win_pct(away, game_date, sport_history, n=10)
    features["form_diff_5"] = features["home_last5_win_pct"] - features["away_last5_win_pct"]
    features["form_diff_10"] = features["home_last10_win_pct"] - features["away_last10_win_pct"]

    # 5. Win/loss streak
    features["home_streak"] = _current_streak(home, game_date, sport_history)
    features["away_streak"] = _current_streak(away, game_date, sport_history)

    # 6. Head-to-head
    h2h = _head_to_head(home, away, game_date, sport_history)
    features["h2h_home_wins"] = h2h["home_wins"]
    features["h2h_away_wins"] = h2h["away_wins"]
    features["h2h_total_games"] = h2h["total"]

    # 7. Scoring averages (points per game, points allowed)
    home_scoring = _scoring_averages(home, game_date, sport_history)
    away_scoring = _scoring_averages(away, game_date, sport_history)
    features["home_ppg"] = home_scoring["ppg"]
    features["home_papg"] = home_scoring["papg"]
    features["away_ppg"] = away_scoring["ppg"]
    features["away_papg"] = away_scoring["papg"]

    # 8. Offensive/defensive efficiency ratings
    features["home_off_rating"] = home_scoring["ppg"]  # simplified
    features["home_def_rating"] = home_scoring["papg"]
    features["away_off_rating"] = away_scoring["ppg"]
    features["away_def_rating"] = away_scoring["papg"]
    features["home_net_rating"] = features["home_off_rating"] - features["home_def_rating"]
    features["away_net_rating"] = features["away_off_rating"] - features["away_def_rating"]

    # 9. Pace proxy — total points per game (higher = faster pace)
    features["home_pace"] = home_scoring["ppg"] + home_scoring["papg"]
    features["away_pace"] = away_scoring["ppg"] + away_scoring["papg"]
    features["combined_pace"] = (features["home_pace"] + features["away_pace"]) / 2

    # 10. Home/away specific performance
    home_at_home = _home_away_record(home, game_date, sport_history, at_home=True)
    away_on_road = _home_away_record(away, game_date, sport_history, at_home=False)
    features["home_home_win_pct"] = home_at_home["win_pct"]
    features["away_road_win_pct"] = away_on_road["win_pct"]

    # 11. Venue (indoor/outdoor)
    features["is_outdoor"] = 1 if sport in OUTDOOR_SPORTS and not game.get("venue_indoor") else 0

    # 12. Weather features (outdoor sports only)
    weather = _get_weather(game) if features["is_outdoor"] else {}
    features["temperature"] = weather.get("temp", 65.0)
    features["wind_speed"] = weather.get("wind_speed", 0.0)
    features["precipitation"] = weather.get("precipitation", 0.0)
    features["humidity"] = weather.get("humidity", 50.0)

    # 13. Season stats from team_stats dict
    home_ts = team_stats.get(home, {}).get("stats", {})
    away_ts = team_stats.get(away, {}).get("stats", {})
    features["home_season_ppg"] = float(home_ts.get("pointsFor", 0)) or features["home_ppg"]
    features["home_season_papg"] = float(home_ts.get("pointsAgainst", 0)) or features["home_papg"]
    features["away_season_ppg"] = float(away_ts.get("pointsFor", 0)) or features["away_ppg"]
    features["away_season_papg"] = float(away_ts.get("pointsAgainst", 0)) or features["away_papg"]

    # 14. Sport encoding (one-hot would be better but ordinal works for trees)
    sport_map = {
        "americanfootball_nfl": 0, "americanfootball_ncaaf": 1,
        "basketball_nba": 2, "basketball_ncaab": 3,
        "baseball_mlb": 4, "icehockey_nhl": 5,
        "soccer_usa_mls": 6, "soccer_epl": 7,
    }
    features["sport_id"] = sport_map.get(sport, -1)

    return features


def build_target(game: dict) -> dict | None:
    """Build target variables from a completed game.

    Returns dict with targets for ML training:
        home_win: 1 if home team won, 0 otherwise
        total_points: combined score
        home_spread: home_score - away_score (negative = home lost by X)
    """
    home_score = game.get("home_score")
    away_score = game.get("away_score")

    if home_score is None or away_score is None:
        return None

    return {
        "home_win": 1 if home_score > away_score else 0,
        "total_points": home_score + away_score,
        "home_spread": home_score - away_score,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> datetime | None:
    """Parse ISO date string."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _parse_record(record: str) -> dict:
    """Parse '10-5' style record string."""
    try:
        parts = record.split("-")
        wins = int(parts[0])
        losses = int(parts[1])
        total = wins + losses
        return {"wins": wins, "losses": losses, "win_pct": wins / total if total else 0.5}
    except (ValueError, IndexError):
        return {"wins": 0, "losses": 0, "win_pct": 0.5}


def _get_team_games(team: str, before_date: datetime, history: list[dict]) -> list[dict]:
    """Get all historical games for a team before a given date, sorted by date desc."""
    games = []
    for g in history:
        gd = _parse_date(g.get("date", ""))
        if not gd or gd >= before_date:
            continue
        if g.get("home_abbr") == team or g.get("away_abbr") == team:
            games.append(g)
    games.sort(key=lambda x: x.get("date", ""), reverse=True)
    return games


def _days_since_last_game(team: str, game_date: datetime, history: list[dict]) -> float:
    """Calculate days since team's last game. Returns 7.0 if unknown."""
    games = _get_team_games(team, game_date, history)
    if not games:
        return 7.0
    last = _parse_date(games[0].get("date", ""))
    if not last:
        return 7.0
    return max((game_date - last).total_seconds() / 86400, 0)


def _recent_win_pct(team: str, game_date: datetime, history: list[dict], n: int) -> float:
    """Win pct over last N games."""
    games = _get_team_games(team, game_date, history)[:n]
    if not games:
        return 0.5

    wins = 0
    for g in games:
        is_home = g.get("home_abbr") == team
        home_score = g.get("home_score", 0) or 0
        away_score = g.get("away_score", 0) or 0
        if is_home and home_score > away_score:
            wins += 1
        elif not is_home and away_score > home_score:
            wins += 1
    return wins / len(games)


def _current_streak(team: str, game_date: datetime, history: list[dict]) -> int:
    """Current win/loss streak. Positive = win streak, negative = loss streak."""
    games = _get_team_games(team, game_date, history)
    if not games:
        return 0

    streak = 0
    streak_type = None

    for g in games:
        is_home = g.get("home_abbr") == team
        home_score = g.get("home_score", 0) or 0
        away_score = g.get("away_score", 0) or 0
        won = (is_home and home_score > away_score) or (not is_home and away_score > home_score)

        if streak_type is None:
            streak_type = won
            streak = 1 if won else -1
        elif won == streak_type:
            streak += 1 if won else -1
        else:
            break

    return streak


def _head_to_head(home: str, away: str, game_date: datetime,
                  history: list[dict]) -> dict:
    """Head-to-head record between two teams."""
    h2h = {"home_wins": 0, "away_wins": 0, "total": 0}
    for g in history:
        gd = _parse_date(g.get("date", ""))
        if not gd or gd >= game_date:
            continue
        teams = {g.get("home_abbr"), g.get("away_abbr")}
        if home in teams and away in teams:
            h2h["total"] += 1
            home_score = g.get("home_score", 0) or 0
            away_score = g.get("away_score", 0) or 0
            # "home_wins" = wins for the team we're calling "home" in the current game
            if g.get("home_abbr") == home and home_score > away_score:
                h2h["home_wins"] += 1
            elif g.get("away_abbr") == home and away_score > home_score:
                h2h["home_wins"] += 1
            else:
                h2h["away_wins"] += 1
    return h2h


def _scoring_averages(team: str, game_date: datetime, history: list[dict]) -> dict:
    """Points per game and points allowed per game."""
    games = _get_team_games(team, game_date, history)[:20]  # last 20 games
    if not games:
        return {"ppg": 100.0, "papg": 100.0}  # neutral default

    scored = []
    allowed = []
    for g in games:
        home_score = g.get("home_score", 0) or 0
        away_score = g.get("away_score", 0) or 0
        if g.get("home_abbr") == team:
            scored.append(home_score)
            allowed.append(away_score)
        else:
            scored.append(away_score)
            allowed.append(home_score)

    return {
        "ppg": np.mean(scored) if scored else 100.0,
        "papg": np.mean(allowed) if allowed else 100.0,
    }


def _home_away_record(team: str, game_date: datetime, history: list[dict],
                      at_home: bool) -> dict:
    """Win pct at home or on the road."""
    games = _get_team_games(team, game_date, history)
    if at_home:
        filtered = [g for g in games if g.get("home_abbr") == team]
    else:
        filtered = [g for g in games if g.get("away_abbr") == team]

    if not filtered:
        return {"win_pct": 0.5}

    wins = 0
    for g in filtered:
        home_score = g.get("home_score", 0) or 0
        away_score = g.get("away_score", 0) or 0
        if at_home and home_score > away_score:
            wins += 1
        elif not at_home and away_score > home_score:
            wins += 1

    return {"win_pct": wins / len(filtered)}


def _get_weather(game: dict) -> dict:
    """Fetch weather for an outdoor game venue. Returns empty dict on failure."""
    if not settings.openweather_api_key:
        return {}

    city = game.get("venue_city", "")
    state = game.get("venue_state", "")
    if not city:
        return {}

    query = f"{city},{state},US" if state else city
    try:
        resp = httpx.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "q": query,
                "appid": settings.openweather_api_key,
                "units": "imperial",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        main = data.get("main", {})
        wind = data.get("wind", {})
        rain = data.get("rain", {})
        snow = data.get("snow", {})
        return {
            "temp": main.get("temp", 65.0),
            "humidity": main.get("humidity", 50.0),
            "wind_speed": wind.get("speed", 0.0),
            "precipitation": rain.get("1h", 0.0) + snow.get("1h", 0.0),
        }
    except httpx.HTTPError:
        return {}


# Feature column order for model training (must be consistent)
FEATURE_COLUMNS = [
    "is_home", "home_win_pct", "away_win_pct", "home_wins", "home_losses",
    "away_wins", "away_losses", "home_rest_days", "away_rest_days", "rest_advantage",
    "home_last5_win_pct", "home_last10_win_pct", "away_last5_win_pct", "away_last10_win_pct",
    "form_diff_5", "form_diff_10", "home_streak", "away_streak",
    "h2h_home_wins", "h2h_away_wins", "h2h_total_games",
    "home_ppg", "home_papg", "away_ppg", "away_papg",
    "home_off_rating", "home_def_rating", "away_off_rating", "away_def_rating",
    "home_net_rating", "away_net_rating",
    "home_pace", "away_pace", "combined_pace",
    "home_home_win_pct", "away_road_win_pct",
    "is_outdoor", "temperature", "wind_speed", "precipitation", "humidity",
    "home_season_ppg", "home_season_papg", "away_season_ppg", "away_season_papg",
    "sport_id",
]


def features_to_array(features: dict) -> list[float]:
    """Convert feature dict to ordered float array for model input."""
    return [float(features.get(col, 0.0)) for col in FEATURE_COLUMNS]
