"""P&L tracker — track bets, results, and lifetime win/loss record.

Persists to JSON. Tracks every bet placed, settles based on game results,
and computes running P&L with $10 flat bet sizing.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from tensorpicks.core.config import settings

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
BETS_FILE = DATA_DIR / "bets.json"
STATS_FILE = DATA_DIR / "stats.json"


def _load_json(path: Path) -> list | dict:
    if path.exists():
        return json.loads(path.read_text())
    return []


def _save_json(path: Path, data) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def place_bet(bet: dict) -> dict:
    """Record a new bet. Returns the bet record with ID and timestamp.

    Args:
        bet: Bet dict from ev.py (type, pick, american_odds, model_prob, ev_pct, etc.)
    """
    bets = _load_json(BETS_FILE)

    bet_size = settings.sports_bettor_bet_size
    decimal_odds = bet.get("decimal_odds", 2.0)

    record = {
        "id": len(bets) + 1,
        "placed_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",  # pending | won | lost | push
        "bet_size": bet_size,
        "potential_payout": round(bet_size * decimal_odds, 2),
        "potential_profit": round(bet_size * (decimal_odds - 1), 2),
        "actual_pnl": 0.0,
        # Copy bet details
        "type": bet.get("type", ""),
        "sport": bet.get("sport", ""),
        "game_id": bet.get("game_id", ""),
        "home_team": bet.get("home_team", ""),
        "away_team": bet.get("away_team", ""),
        "pick": bet.get("pick", ""),
        "side": bet.get("side", ""),
        "bookmaker": bet.get("bookmaker", ""),
        "american_odds": bet.get("american_odds", 0),
        "decimal_odds": decimal_odds,
        "point": bet.get("point"),
        "model_prob": bet.get("model_prob", 0),
        "implied_prob": bet.get("implied_prob", 0),
        "ev_pct": bet.get("ev_pct", 0),
        "edge": bet.get("edge", 0),
        "kelly_fraction": bet.get("kelly_fraction", 0),
    }

    bets.append(record)
    _save_json(BETS_FILE, bets)
    log.info("Bet #%d placed: %s %s @ %s ($%.2f)",
             record["id"], record["type"], record["pick"],
             record["bookmaker"], bet_size)

    return record


def settle_bet(bet_id: int, result: str, actual_score: dict | None = None) -> dict | None:
    """Settle a pending bet.

    Args:
        bet_id: Bet record ID
        result: "won", "lost", or "push"
        actual_score: Optional dict with home_score, away_score

    Returns updated bet record or None.
    """
    bets = _load_json(BETS_FILE)

    for bet in bets:
        if bet["id"] == bet_id:
            if bet["status"] != "pending":
                log.warning("Bet #%d already settled: %s", bet_id, bet["status"])
                return bet

            bet["status"] = result
            bet["settled_at"] = datetime.now(timezone.utc).isoformat()
            if actual_score:
                bet["actual_score"] = actual_score

            if result == "won":
                bet["actual_pnl"] = bet["potential_profit"]
            elif result == "lost":
                bet["actual_pnl"] = -bet["bet_size"]
            else:  # push
                bet["actual_pnl"] = 0.0

            _save_json(BETS_FILE, bets)
            log.info("Bet #%d settled: %s (PnL: $%.2f)",
                     bet_id, result, bet["actual_pnl"])
            return bet

    log.warning("Bet #%d not found", bet_id)
    return None


def settle_from_scores(scores: list[dict]) -> list[dict]:
    """Auto-settle pending bets using game scores.

    Args:
        scores: List of game score dicts from odds.py get_scores()

    Returns list of settled bet records.
    """
    bets = _load_json(BETS_FILE)
    pending = [b for b in bets if b["status"] == "pending"]
    settled = []

    # Build score lookup by game_id
    score_map = {}
    for score in scores:
        if score.get("completed"):
            game_id = score.get("id", "")
            home_score = away_score = None
            for s in score.get("scores", []):
                if s.get("name") == score.get("home_team"):
                    home_score = int(s.get("score", 0))
                else:
                    away_score = int(s.get("score", 0))
            if home_score is not None and away_score is not None:
                score_map[game_id] = {
                    "home_team": score.get("home_team"),
                    "away_team": score.get("away_team"),
                    "home_score": home_score,
                    "away_score": away_score,
                }

    for bet in pending:
        game_id = bet.get("game_id", "")
        if game_id not in score_map:
            continue

        actual = score_map[game_id]
        result = _determine_result(bet, actual)

        if result:
            settled_bet = settle_bet(bet["id"], result, actual)
            if settled_bet:
                settled.append(settled_bet)

    return settled


def _determine_result(bet: dict, score: dict) -> str | None:
    """Determine if a bet won, lost, or pushed based on actual score."""
    home_score = score["home_score"]
    away_score = score["away_score"]
    bet_type = bet.get("type", "")

    if bet_type == "moneyline":
        pick = bet.get("pick", "")
        home_team = bet.get("home_team", "")
        if pick == home_team:
            if home_score > away_score:
                return "won"
            elif home_score < away_score:
                return "lost"
            return "push"
        else:
            if away_score > home_score:
                return "won"
            elif away_score < home_score:
                return "lost"
            return "push"

    elif bet_type == "spread":
        point = bet.get("point", 0)
        side = bet.get("side", "")
        actual_spread = home_score - away_score

        if side == "home":
            # Home +point (e.g., home -7 means point=-7)
            result_with_spread = actual_spread + point
        else:
            result_with_spread = -actual_spread + (-point if point else 0)

        if result_with_spread > 0:
            return "won"
        elif result_with_spread < 0:
            return "lost"
        return "push"

    elif bet_type == "total":
        point = bet.get("point", 0)
        total = home_score + away_score
        side = bet.get("side", "")

        if side == "over":
            if total > point:
                return "won"
            elif total < point:
                return "lost"
            return "push"
        else:  # under
            if total < point:
                return "won"
            elif total > point:
                return "lost"
            return "push"

    return None


def get_stats() -> dict:
    """Compute lifetime statistics.

    Returns:
        total_bets, pending, won, lost, pushed,
        win_rate, total_wagered, total_pnl, roi,
        best_bet, worst_bet, streak, by_sport, by_type
    """
    bets = _load_json(BETS_FILE)

    total = len(bets)
    pending = sum(1 for b in bets if b["status"] == "pending")
    won = sum(1 for b in bets if b["status"] == "won")
    lost = sum(1 for b in bets if b["status"] == "lost")
    pushed = sum(1 for b in bets if b["status"] == "push")
    settled = won + lost + pushed

    total_pnl = sum(b.get("actual_pnl", 0) for b in bets)
    total_wagered = sum(b.get("bet_size", 0) for b in bets if b["status"] != "pending")

    win_rate = (won / settled * 100) if settled > 0 else 0.0
    roi = (total_pnl / total_wagered * 100) if total_wagered > 0 else 0.0

    # Best and worst bets
    settled_bets = [b for b in bets if b["status"] in ("won", "lost")]
    best_bet = max(settled_bets, key=lambda b: b.get("actual_pnl", 0)) if settled_bets else None
    worst_bet = min(settled_bets, key=lambda b: b.get("actual_pnl", 0)) if settled_bets else None

    # Current streak
    streak = _current_streak(bets)

    # Breakdown by sport
    by_sport = _breakdown(bets, "sport")

    # Breakdown by bet type
    by_type = _breakdown(bets, "type")

    return {
        "total_bets": total,
        "pending": pending,
        "won": won,
        "lost": lost,
        "pushed": pushed,
        "win_rate": win_rate,
        "total_wagered": total_wagered,
        "total_pnl": total_pnl,
        "roi": roi,
        "bankroll": settings.sports_bettor_bankroll + total_pnl,
        "best_bet": best_bet,
        "worst_bet": worst_bet,
        "streak": streak,
        "by_sport": by_sport,
        "by_type": by_type,
    }


def _current_streak(bets: list[dict]) -> str:
    """Calculate current win/loss streak."""
    settled = [b for b in bets if b["status"] in ("won", "lost")]
    settled.sort(key=lambda b: b.get("settled_at", ""), reverse=True)

    if not settled:
        return "N/A"

    streak_type = settled[0]["status"]
    count = 0
    for b in settled:
        if b["status"] == streak_type:
            count += 1
        else:
            break

    prefix = "W" if streak_type == "won" else "L"
    return f"{prefix}{count}"


def _breakdown(bets: list[dict], key: str) -> dict:
    """Break down stats by a given key (sport, type, etc.)."""
    groups = {}
    for b in bets:
        if b["status"] == "pending":
            continue
        val = b.get(key, "unknown")
        if val not in groups:
            groups[val] = {"won": 0, "lost": 0, "pushed": 0, "pnl": 0.0}
        groups[val][b["status"]] = groups[val].get(b["status"], 0) + 1
        groups[val]["pnl"] += b.get("actual_pnl", 0)

    for val, g in groups.items():
        total = g["won"] + g["lost"] + g["pushed"]
        g["win_rate"] = (g["won"] / total * 100) if total > 0 else 0.0

    return groups


def get_pending_bets() -> list[dict]:
    """Get all unsettled bets."""
    bets = _load_json(BETS_FILE)
    return [b for b in bets if b["status"] == "pending"]


def format_stats(stats: dict) -> str:
    """Format stats as a readable summary string."""
    pnl = stats["total_pnl"]
    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"

    lines = [
        f"Record: {stats['won']}W - {stats['lost']}L - {stats['pushed']}P "
        f"({stats['win_rate']:.1f}%)",
        f"Total PnL: {pnl_str} | ROI: {stats['roi']:.1f}%",
        f"Bankroll: ${stats['bankroll']:.2f} | Streak: {stats['streak']}",
        f"Total bets: {stats['total_bets']} | Pending: {stats['pending']}",
    ]

    if stats["by_sport"]:
        lines.append("\nBy Sport:")
        for sport, data in sorted(stats["by_sport"].items()):
            s_pnl = data["pnl"]
            s_pnl_str = f"+${s_pnl:.2f}" if s_pnl >= 0 else f"-${abs(s_pnl):.2f}"
            lines.append(
                f"  {sport}: {data['won']}W-{data['lost']}L "
                f"({data['win_rate']:.0f}%) {s_pnl_str}"
            )

    if stats["by_type"]:
        lines.append("\nBy Type:")
        for btype, data in sorted(stats["by_type"].items()):
            t_pnl = data["pnl"]
            t_pnl_str = f"+${t_pnl:.2f}" if t_pnl >= 0 else f"-${abs(t_pnl):.2f}"
            lines.append(
                f"  {btype}: {data['won']}W-{data['lost']}L "
                f"({data['win_rate']:.0f}%) {t_pnl_str}"
            )

    return "\n".join(lines)
