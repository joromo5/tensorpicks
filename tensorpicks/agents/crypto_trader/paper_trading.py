"""Paper trading engine — simulates a real portfolio with fake money."""

import json
import logging
from datetime import datetime
from pathlib import Path

from tensorpicks.core.config import settings

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
TRADE_LOG_FILE = DATA_DIR / "trades.json"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_portfolio() -> dict:
    """Load or initialize the paper trading portfolio."""
    _ensure_data_dir()
    if PORTFOLIO_FILE.exists():
        return json.loads(PORTFOLIO_FILE.read_text())

    portfolio = {
        "cash": settings.crypto_paper_balance,
        "positions": {},
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl": 0.0,
        "created_at": datetime.now().isoformat(),
    }
    _save_portfolio(portfolio)
    return portfolio


def _save_portfolio(portfolio: dict):
    _ensure_data_dir()
    PORTFOLIO_FILE.write_text(json.dumps(portfolio, indent=2, default=str))


def _log_trade(trade: dict):
    _ensure_data_dir()
    trades = []
    if TRADE_LOG_FILE.exists():
        trades = json.loads(TRADE_LOG_FILE.read_text())
    trades.append(trade)
    TRADE_LOG_FILE.write_text(json.dumps(trades, indent=2, default=str))


def get_portfolio_value(current_prices: dict) -> float:
    """Calculate total portfolio value (cash + positions at current prices)."""
    portfolio = load_portfolio()
    total = portfolio["cash"]

    for coin_id, pos in portfolio["positions"].items():
        price_data = current_prices.get(coin_id, {})
        price = price_data.get("price", pos.get("entry_price", 0))
        total += pos["quantity"] * price

    return total


def open_position(
    coin_id: str,
    symbol: str,
    side: str,  # "long" or "short"
    quantity: float,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    atr: float,
    reasons: list[str],
) -> dict | None:
    """Open a new paper trade position."""
    portfolio = load_portfolio()
    cost = quantity * entry_price

    if side == "long" and cost > portfolio["cash"]:
        log.warning("Insufficient cash ($%.2f) for $%.2f position", portfolio["cash"], cost)
        return None

    if side == "long":
        portfolio["cash"] -= cost

    risk_usd = abs(entry_price - stop_loss) * quantity

    position = {
        "coin_id": coin_id,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "atr": atr,
        "risk_usd": risk_usd,
        "opened_at": datetime.now().isoformat(),
        "reasons": reasons,
    }

    portfolio["positions"][coin_id] = position
    portfolio["total_trades"] += 1
    _save_portfolio(portfolio)

    _log_trade({
        "action": "OPEN",
        "side": side,
        "coin_id": coin_id,
        "symbol": symbol,
        "quantity": quantity,
        "price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "timestamp": datetime.now().isoformat(),
    })

    log.info(
        "Opened %s %s: %.8f @ $%.6f (SL: $%.6f, TP: $%.6f)",
        side.upper(), symbol, quantity, entry_price, stop_loss, take_profit,
    )
    return position


def close_position(coin_id: str, exit_price: float, reason: str) -> dict | None:
    """Close an open paper trade position. Returns trade summary."""
    portfolio = load_portfolio()

    if coin_id not in portfolio["positions"]:
        log.warning("No open position for %s", coin_id)
        return None

    pos = portfolio["positions"].pop(coin_id)

    if pos["side"] == "long":
        pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
        portfolio["cash"] += pos["quantity"] * exit_price
    else:
        pnl = (pos["entry_price"] - exit_price) * pos["quantity"]
        portfolio["cash"] += pnl  # For paper shorts, just add PnL

    pnl_pct = (pnl / (pos["entry_price"] * pos["quantity"])) * 100
    portfolio["total_pnl"] += pnl

    if pnl > 0:
        portfolio["wins"] += 1
    else:
        portfolio["losses"] += 1

    _save_portfolio(portfolio)

    trade_summary = {
        "action": "CLOSE",
        "reason": reason,
        "coin_id": coin_id,
        "symbol": pos["symbol"],
        "side": pos["side"],
        "quantity": pos["quantity"],
        "entry_price": pos["entry_price"],
        "exit_price": exit_price,
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "held_since": pos["opened_at"],
        "timestamp": datetime.now().isoformat(),
    }

    _log_trade(trade_summary)

    log.info(
        "Closed %s %s @ $%.6f — PnL: $%.2f (%.2f%%) [%s]",
        pos["side"].upper(), pos["symbol"], exit_price, pnl, pnl_pct, reason,
    )
    return trade_summary


def update_stop_loss(coin_id: str, new_stop: float):
    """Update the stop loss for an open position (trailing stop)."""
    portfolio = load_portfolio()
    if coin_id in portfolio["positions"]:
        portfolio["positions"][coin_id]["stop_loss"] = new_stop
        _save_portfolio(portfolio)


def get_stats() -> dict:
    """Get overall paper trading performance stats."""
    portfolio = load_portfolio()
    total_trades = portfolio["total_trades"]
    wins = portfolio["wins"]
    losses = portfolio["losses"]

    return {
        "cash": round(portfolio["cash"], 2),
        "open_positions": len(portfolio["positions"]),
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total_trades * 100) if total_trades > 0 else 0, 1),
        "total_pnl": round(portfolio["total_pnl"], 2),
        "positions": portfolio["positions"],
    }


def reset_portfolio():
    """Reset the paper trading portfolio to starting balance."""
    portfolio = {
        "cash": settings.crypto_paper_balance,
        "positions": {},
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl": 0.0,
        "created_at": datetime.now().isoformat(),
    }
    _save_portfolio(portfolio)

    # Also clear trade log
    _ensure_data_dir()
    TRADE_LOG_FILE.write_text("[]")
    log.info("Paper portfolio reset to $%.2f", settings.crypto_paper_balance)
