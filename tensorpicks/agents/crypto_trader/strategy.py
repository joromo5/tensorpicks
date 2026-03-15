"""Swing trading strategy engine — generates BUY/SELL/HOLD signals."""

import logging
from dataclasses import dataclass
from enum import Enum

from tensorpicks.agents.crypto_trader.analysis import Indicators

log = logging.getLogger(__name__)


class Signal(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class TradeSignal:
    """A trading signal with reasoning."""

    coin_id: str
    symbol: str
    signal: Signal
    confidence: float  # 0.0 - 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    reasons: list[str]


def evaluate(coin_id: str, indicators: Indicators, price_data: dict) -> TradeSignal:
    """Evaluate all indicators and produce a swing trade signal.

    Uses a scoring system: each indicator contributes points toward
    bullish (+) or bearish (-). Final score determines signal.
    """
    score = 0.0
    reasons = []
    price = indicators.price

    # --- RSI ---
    if indicators.rsi_14 is not None:
        if indicators.rsi_14 < 30:
            score += 2
            reasons.append(f"RSI oversold ({indicators.rsi_14:.1f})")
        elif indicators.rsi_14 < 40:
            score += 1
            reasons.append(f"RSI approaching oversold ({indicators.rsi_14:.1f})")
        elif indicators.rsi_14 > 70:
            score -= 2
            reasons.append(f"RSI overbought ({indicators.rsi_14:.1f})")
        elif indicators.rsi_14 > 60:
            score -= 1
            reasons.append(f"RSI approaching overbought ({indicators.rsi_14:.1f})")

    # --- MACD ---
    if indicators.macd_histogram is not None:
        if indicators.macd_histogram > 0 and indicators.macd_line > indicators.macd_signal:
            score += 1.5
            reasons.append("MACD bullish crossover")
        elif indicators.macd_histogram < 0 and indicators.macd_line < indicators.macd_signal:
            score -= 1.5
            reasons.append("MACD bearish crossover")

    # --- Moving Average Trend ---
    if indicators.sma_20 and indicators.sma_50:
        if indicators.sma_20 > indicators.sma_50 and price > indicators.sma_20:
            score += 1.5
            reasons.append("Price above rising MAs (uptrend)")
        elif indicators.sma_20 < indicators.sma_50 and price < indicators.sma_20:
            score -= 1.5
            reasons.append("Price below falling MAs (downtrend)")

        # Golden cross / death cross proximity
        ma_ratio = indicators.sma_20 / indicators.sma_50
        if 0.98 < ma_ratio < 1.02:
            if indicators.sma_20 > indicators.sma_50:
                score += 1
                reasons.append("Potential golden cross forming")
            else:
                score -= 1
                reasons.append("Potential death cross forming")

    # --- Bollinger Bands ---
    if indicators.bb_lower and indicators.bb_upper:
        bb_width = (indicators.bb_upper - indicators.bb_lower) / indicators.bb_middle
        if price <= indicators.bb_lower:
            score += 1.5
            reasons.append("Price at lower Bollinger Band (potential bounce)")
        elif price >= indicators.bb_upper:
            score -= 1.5
            reasons.append("Price at upper Bollinger Band (potential pullback)")

        # Squeeze detection (low volatility → breakout coming)
        if bb_width < 0.04:
            reasons.append("Bollinger squeeze detected — breakout imminent")

    # --- Volume Confirmation ---
    if indicators.volume_ratio is not None:
        if indicators.volume_ratio > 1.5:
            # High volume confirms the current direction
            if score > 0:
                score += 1
                reasons.append(f"High volume confirms bullish move ({indicators.volume_ratio:.1f}x avg)")
            elif score < 0:
                score -= 1
                reasons.append(f"High volume confirms bearish move ({indicators.volume_ratio:.1f}x avg)")
        elif indicators.volume_ratio < 0.5:
            reasons.append("Low volume — weak conviction in current move")

    # --- Support / Resistance ---
    if indicators.support and indicators.resistance:
        range_size = indicators.resistance - indicators.support
        if range_size > 0:
            position_in_range = (price - indicators.support) / range_size
            if position_in_range < 0.15:
                score += 1
                reasons.append("Price near support level")
            elif position_in_range > 0.85:
                score -= 1
                reasons.append("Price near resistance level")

    # --- 24h Momentum ---
    change_24h = price_data.get("change_24h", 0) or 0
    if change_24h < -8:
        score += 0.5
        reasons.append(f"Sharp 24h drop ({change_24h:.1f}%) — potential reversal")
    elif change_24h > 8:
        score -= 0.5
        reasons.append(f"Sharp 24h pump ({change_24h:.1f}%) — potential pullback")

    # --- Determine Signal ---
    if score >= 4:
        signal = Signal.STRONG_BUY
    elif score >= 2:
        signal = Signal.BUY
    elif score <= -4:
        signal = Signal.STRONG_SELL
    elif score <= -2:
        signal = Signal.SELL
    else:
        signal = Signal.HOLD

    confidence = min(abs(score) / 6, 1.0)

    # --- Stop Loss & Take Profit ---
    atr = indicators.atr_14 or (price * 0.03)  # fallback 3%

    if signal in (Signal.BUY, Signal.STRONG_BUY):
        stop_loss = price - (atr * 1.5)
        take_profit = price + (atr * 3)  # 2:1 reward/risk
    elif signal in (Signal.SELL, Signal.STRONG_SELL):
        stop_loss = price + (atr * 1.5)
        take_profit = price - (atr * 3)
    else:
        stop_loss = price - (atr * 1.5)
        take_profit = price + (atr * 1.5)

    return TradeSignal(
        coin_id=coin_id,
        symbol=indicators.symbol,
        signal=signal,
        confidence=confidence,
        entry_price=price,
        stop_loss=round(stop_loss, 6),
        take_profit=round(take_profit, 6),
        reasons=reasons,
    )
