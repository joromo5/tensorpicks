"""Fetch market data from CoinGecko (historical + fundamentals) and Binance (real-time)."""

import logging
import time
from datetime import datetime, timedelta

import httpx

log = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
BINANCE_BASE = "https://api.binance.com/api/v3"

# Top 10 crypto by volume — CoinGecko IDs → Binance symbols
COINS = {
    "bitcoin": {"symbol": "BTC", "binance": "BTCUSDT"},
    "ethereum": {"symbol": "ETH", "binance": "ETHUSDT"},
    "solana": {"symbol": "SOL", "binance": "SOLUSDT"},
    "dogecoin": {"symbol": "DOGE", "binance": "DOGEUSDT"},
    "cardano": {"symbol": "ADA", "binance": "ADAUSDT"},
    "ripple": {"symbol": "XRP", "binance": "XRPUSDT"},
    "avalanche-2": {"symbol": "AVAX", "binance": "AVAXUSDT"},
    "chainlink": {"symbol": "LINK", "binance": "LINKUSDT"},
    "matic-network": {"symbol": "MATIC", "binance": "MATICUSDT"},
    "polkadot": {"symbol": "DOT", "binance": "DOTUSDT"},
}


def get_current_prices() -> dict[str, dict]:
    """Get current prices, 24h change, and volume for all tracked coins.

    Returns: {coin_id: {price, change_24h, volume_24h, market_cap, symbol}}
    """
    ids = ",".join(COINS.keys())
    try:
        resp = httpx.get(
            f"{COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": ids,
                "order": "market_cap_desc",
                "sparkline": "false",
                "price_change_percentage": "1h,24h,7d",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        result = {}
        for coin in data:
            result[coin["id"]] = {
                "symbol": coin["symbol"].upper(),
                "price": coin["current_price"],
                "change_1h": coin.get("price_change_percentage_1h_in_currency", 0),
                "change_24h": coin.get("price_change_percentage_24h_in_currency", 0),
                "change_7d": coin.get("price_change_percentage_7d_in_currency", 0),
                "volume_24h": coin["total_volume"],
                "market_cap": coin["market_cap"],
                "high_24h": coin["high_24h"],
                "low_24h": coin["low_24h"],
            }
        return result
    except httpx.HTTPError as e:
        log.error("CoinGecko price fetch failed: %s", e)
        return {}


def get_klines(
    coin_id: str,
    interval: str = "4h",
    limit: int = 100,
) -> list[dict]:
    """Get candlestick (OHLCV) data from Binance.

    Args:
        coin_id: CoinGecko ID (e.g. "bitcoin")
        interval: Binance kline interval (1m, 5m, 15m, 1h, 4h, 1d, 1w)
        limit: Number of candles (max 1000)

    Returns: List of {time, open, high, low, close, volume}
    """
    binance_symbol = COINS.get(coin_id, {}).get("binance")
    if not binance_symbol:
        log.error("Unknown coin_id: %s", coin_id)
        return []

    try:
        resp = httpx.get(
            f"{BINANCE_BASE}/klines",
            params={
                "symbol": binance_symbol,
                "interval": interval,
                "limit": limit,
            },
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()

        candles = []
        for k in raw:
            candles.append({
                "time": datetime.fromtimestamp(k[0] / 1000),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })
        return candles
    except httpx.HTTPError as e:
        log.error("Binance klines fetch failed for %s: %s", binance_symbol, e)
        return []


def get_order_book(coin_id: str, limit: int = 20) -> dict:
    """Get order book depth from Binance.

    Returns: {bids: [[price, qty], ...], asks: [[price, qty], ...]}
    """
    binance_symbol = COINS.get(coin_id, {}).get("binance")
    if not binance_symbol:
        return {}

    try:
        resp = httpx.get(
            f"{BINANCE_BASE}/depth",
            params={"symbol": binance_symbol, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "bids": [[float(p), float(q)] for p, q in data.get("bids", [])],
            "asks": [[float(p), float(q)] for p, q in data.get("asks", [])],
        }
    except httpx.HTTPError as e:
        log.error("Binance order book fetch failed: %s", e)
        return {}
