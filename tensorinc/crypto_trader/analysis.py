"""Technical analysis indicators for crypto swing trading."""

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class Indicators:
    """All computed indicators for a single coin."""

    symbol: str
    price: float

    # Moving averages
    sma_20: float | None = None
    sma_50: float | None = None
    ema_12: float | None = None
    ema_26: float | None = None

    # MACD
    macd_line: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None

    # RSI
    rsi_14: float | None = None

    # Bollinger Bands
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None

    # Volume
    volume_sma_20: float | None = None
    current_volume: float | None = None
    volume_ratio: float | None = None  # current / avg

    # Support / Resistance
    support: float | None = None
    resistance: float | None = None

    # ATR (Average True Range) for stop loss calculation
    atr_14: float | None = None


def compute_indicators(candles: list[dict], symbol: str = "") -> Indicators | None:
    """Compute all technical indicators from OHLCV candle data.

    Args:
        candles: List of {time, open, high, low, close, volume} dicts
        symbol: Coin symbol for labeling

    Returns: Indicators dataclass or None if insufficient data
    """
    if len(candles) < 50:
        log.warning("Not enough candles (%d) for full analysis", len(candles))
        return None

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]
    price = closes[-1]

    ind = Indicators(symbol=symbol, price=price)

    # --- Moving Averages ---
    ind.sma_20 = _sma(closes, 20)
    ind.sma_50 = _sma(closes, 50)
    ind.ema_12 = _ema(closes, 12)
    ind.ema_26 = _ema(closes, 26)

    # --- MACD ---
    if ind.ema_12 is not None and ind.ema_26 is not None:
        # Compute full MACD line series for signal line
        macd_series = []
        ema12_series = _ema_series(closes, 12)
        ema26_series = _ema_series(closes, 26)
        min_len = min(len(ema12_series), len(ema26_series))
        for i in range(min_len):
            offset12 = len(ema12_series) - min_len
            offset26 = len(ema26_series) - min_len
            macd_series.append(ema12_series[offset12 + i] - ema26_series[offset26 + i])

        ind.macd_line = macd_series[-1] if macd_series else None

        if len(macd_series) >= 9:
            signal_series = _ema_series(macd_series, 9)
            ind.macd_signal = signal_series[-1] if signal_series else None
            if ind.macd_line is not None and ind.macd_signal is not None:
                ind.macd_histogram = ind.macd_line - ind.macd_signal

    # --- RSI ---
    ind.rsi_14 = _rsi(closes, 14)

    # --- Bollinger Bands ---
    if len(closes) >= 20:
        sma20 = ind.sma_20
        std20 = _stddev(closes[-20:])
        if sma20 and std20:
            ind.bb_upper = sma20 + (2 * std20)
            ind.bb_middle = sma20
            ind.bb_lower = sma20 - (2 * std20)

    # --- Volume ---
    ind.volume_sma_20 = _sma(volumes, 20)
    ind.current_volume = volumes[-1]
    if ind.volume_sma_20 and ind.volume_sma_20 > 0:
        ind.volume_ratio = ind.current_volume / ind.volume_sma_20

    # --- Support / Resistance (swing highs/lows from last 50 candles) ---
    recent_lows = lows[-50:]
    recent_highs = highs[-50:]
    ind.support = min(recent_lows)
    ind.resistance = max(recent_highs)

    # --- ATR ---
    ind.atr_14 = _atr(highs, lows, closes, 14)

    return ind


# ---------- helpers ----------


def _sma(data: list[float], period: int) -> float | None:
    if len(data) < period:
        return None
    return sum(data[-period:]) / period


def _ema(data: list[float], period: int) -> float | None:
    series = _ema_series(data, period)
    return series[-1] if series else None


def _ema_series(data: list[float], period: int) -> list[float]:
    if len(data) < period:
        return []
    k = 2 / (period + 1)
    ema_vals = [sum(data[:period]) / period]
    for val in data[period:]:
        ema_vals.append(val * k + ema_vals[-1] * (1 - k))
    return ema_vals


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _stddev(data: list[float]) -> float | None:
    if len(data) < 2:
        return None
    mean = sum(data) / len(data)
    variance = sum((x - mean) ** 2 for x in data) / len(data)
    return variance ** 0.5


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(highs) < period + 1:
        return None

    true_ranges = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    atr = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period

    return atr
