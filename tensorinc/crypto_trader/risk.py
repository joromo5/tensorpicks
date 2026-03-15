"""Risk management — position sizing, stop losses, portfolio limits."""

import logging
from dataclasses import dataclass

from tensorinc.crypto_trader.strategy import TradeSignal, Signal
from tensorinc.core.config import settings

log = logging.getLogger(__name__)

# Max % of portfolio in a single position
MAX_POSITION_PCT = 0.20  # 20%

# Max % of portfolio at risk across all positions
MAX_TOTAL_RISK_PCT = 0.10  # 10%

# Max number of open positions
MAX_OPEN_POSITIONS = 5

# Risk per trade (moderate profile): 2-5% of portfolio
RISK_PER_TRADE_PCT = 0.03  # 3%


@dataclass
class PositionSize:
    """Calculated position size for a trade."""

    coin_id: str
    symbol: str
    quantity: float
    usd_value: float
    risk_usd: float
    risk_pct: float
    approved: bool
    rejection_reason: str | None = None


def calculate_position(
    signal: TradeSignal,
    portfolio_value: float,
    open_positions: dict[str, dict],
) -> PositionSize:
    """Calculate position size based on risk management rules.

    Uses the ATR-based stop loss to determine position size such that
    max loss per trade = RISK_PER_TRADE_PCT of portfolio.
    """
    symbol = signal.symbol
    price = signal.entry_price

    # --- Check if we already hold this coin ---
    if signal.coin_id in open_positions:
        return PositionSize(
            coin_id=signal.coin_id,
            symbol=symbol,
            quantity=0,
            usd_value=0,
            risk_usd=0,
            risk_pct=0,
            approved=False,
            rejection_reason=f"Already holding {symbol}",
        )

    # --- Check max open positions ---
    if len(open_positions) >= MAX_OPEN_POSITIONS:
        return PositionSize(
            coin_id=signal.coin_id,
            symbol=symbol,
            quantity=0,
            usd_value=0,
            risk_usd=0,
            risk_pct=0,
            approved=False,
            rejection_reason=f"Max positions reached ({MAX_OPEN_POSITIONS})",
        )

    # --- Calculate risk per unit ---
    if signal.signal in (Signal.BUY, Signal.STRONG_BUY):
        risk_per_unit = abs(price - signal.stop_loss)
    else:
        risk_per_unit = abs(signal.stop_loss - price)

    if risk_per_unit <= 0:
        return PositionSize(
            coin_id=signal.coin_id,
            symbol=symbol,
            quantity=0,
            usd_value=0,
            risk_usd=0,
            risk_pct=0,
            approved=False,
            rejection_reason="Invalid stop loss distance",
        )

    # --- Position size from risk budget ---
    risk_budget = portfolio_value * RISK_PER_TRADE_PCT
    quantity = risk_budget / risk_per_unit
    usd_value = quantity * price

    # --- Cap at max position size ---
    max_usd = portfolio_value * MAX_POSITION_PCT
    if usd_value > max_usd:
        usd_value = max_usd
        quantity = usd_value / price

    # --- Check total portfolio risk ---
    current_risk = sum(
        pos.get("risk_usd", 0) for pos in open_positions.values()
    )
    max_total_risk = portfolio_value * MAX_TOTAL_RISK_PCT
    actual_risk = quantity * risk_per_unit

    if current_risk + actual_risk > max_total_risk:
        # Scale down to fit within risk budget
        available_risk = max_total_risk - current_risk
        if available_risk <= 0:
            return PositionSize(
                coin_id=signal.coin_id,
                symbol=symbol,
                quantity=0,
                usd_value=0,
                risk_usd=0,
                risk_pct=0,
                approved=False,
                rejection_reason="Total portfolio risk limit reached",
            )
        quantity = available_risk / risk_per_unit
        usd_value = quantity * price
        actual_risk = available_risk

    risk_pct = (actual_risk / portfolio_value) * 100

    return PositionSize(
        coin_id=signal.coin_id,
        symbol=symbol,
        quantity=round(quantity, 8),
        usd_value=round(usd_value, 2),
        risk_usd=round(actual_risk, 2),
        risk_pct=round(risk_pct, 2),
        approved=True,
    )


def check_stop_loss(position: dict, current_price: float) -> str | None:
    """Check if a position's stop loss or take profit has been hit.

    Returns: "stop_loss", "take_profit", or None
    """
    side = position.get("side", "long")

    if side == "long":
        if current_price <= position["stop_loss"]:
            return "stop_loss"
        if current_price >= position["take_profit"]:
            return "take_profit"
    else:  # short
        if current_price >= position["stop_loss"]:
            return "stop_loss"
        if current_price <= position["take_profit"]:
            return "take_profit"

    return None


def update_trailing_stop(position: dict, current_price: float) -> dict:
    """Update trailing stop loss — moves stop up as price increases (long positions).

    Trail distance = 2x ATR from entry, but only moves up, never down.
    """
    side = position.get("side", "long")
    atr = position.get("atr", 0)

    if atr <= 0:
        return position

    trail_distance = atr * 1.5

    if side == "long":
        new_stop = current_price - trail_distance
        if new_stop > position["stop_loss"]:
            position["stop_loss"] = round(new_stop, 6)
            log.info(
                "Trailing stop updated for %s: $%.6f",
                position["symbol"], position["stop_loss"],
            )
    else:
        new_stop = current_price + trail_distance
        if new_stop < position["stop_loss"]:
            position["stop_loss"] = round(new_stop, 6)

    return position
