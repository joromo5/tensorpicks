"""Crypto Trading Agent — swing trades top 10 crypto with paper/live trading."""

import logging

from tensorinc.core.agent import Agent
from tensorinc.core import slack
from tensorinc.core.config import settings
from tensorinc.crypto_trader.market_data import (
    get_current_prices,
    get_klines,
    COINS,
)
from tensorinc.crypto_trader.analysis import compute_indicators
from tensorinc.crypto_trader.strategy import evaluate, Signal
from tensorinc.crypto_trader.risk import (
    calculate_position,
    check_stop_loss,
    update_trailing_stop,
)
from tensorinc.crypto_trader import paper_trading

log = logging.getLogger(__name__)

SIGNAL_EMOJI = {
    Signal.STRONG_BUY: "🟢🟢",
    Signal.BUY: "🟢",
    Signal.HOLD: "⚪",
    Signal.SELL: "🔴",
    Signal.STRONG_SELL: "🔴🔴",
}

TRADE_OPEN_MSG = """💰 *Crypto Trade — {side} {symbol}*

{emoji} *{signal}* (confidence: {confidence:.0%})

*Entry:* ${entry:.6f}
*Stop Loss:* ${stop_loss:.6f}
*Take Profit:* ${take_profit:.6f}
*Position Size:* {quantity:.8f} {symbol} (${usd_value:.2f})
*Risk:* ${risk_usd:.2f} ({risk_pct:.1f}% of portfolio)

*Reasons:*
{reasons}

_Paper trading mode_"""

TRADE_CLOSE_MSG = """📊 *Crypto Trade Closed — {symbol}*

*{reason}*
*Entry:* ${entry:.6f} → *Exit:* ${exit:.6f}
*PnL:* {pnl_sign}${pnl_abs:.2f} ({pnl_pct:+.2f}%)
*Held since:* {held_since}

_Paper trading mode_"""

SCAN_SUMMARY_MSG = """📈 *Crypto Scan — Market Overview*

{signals}

💼 *Portfolio:*
Cash: ${cash:.2f}
Open positions: {open_positions}
Total trades: {total_trades} | Win rate: {win_rate:.1f}%
Total PnL: {pnl_sign}${pnl_abs:.2f}

_Paper trading — starting balance: ${starting_balance:.2f}_"""


class CryptoTraderAgent(Agent):
    name = "crypto_trader"

    def run(self) -> None:
        self.log.info("Starting crypto scan...")

        # 1. Fetch current prices for all coins
        prices = get_current_prices()
        if not prices:
            slack.post("⚠️ Crypto Trader: Could not fetch market data")
            return

        # 2. Check existing positions for stop loss / take profit hits
        self._check_open_positions(prices)

        # 3. Analyze each coin
        signals = []
        for coin_id in COINS:
            if coin_id not in prices:
                continue

            coin_info = COINS[coin_id]
            symbol = coin_info["symbol"]

            # Get 4h candles for swing trading analysis
            candles = get_klines(coin_id, interval="4h", limit=100)
            if not candles:
                continue

            # Compute technical indicators
            indicators = compute_indicators(candles, symbol=symbol)
            if not indicators:
                continue

            # Generate trade signal
            signal = evaluate(coin_id, indicators, prices[coin_id])
            signals.append(signal)

            # Execute trades for BUY / STRONG_BUY signals
            if signal.signal in (Signal.BUY, Signal.STRONG_BUY):
                self._execute_buy(signal, indicators, prices)

        # 4. Post market scan summary
        self._post_summary(signals, prices)

        self.log.info("Crypto scan complete — evaluated %d coins", len(signals))

    def _check_open_positions(self, prices: dict):
        """Check all open positions for stop loss / take profit / trailing stop."""
        portfolio = paper_trading.load_portfolio()

        for coin_id, pos in list(portfolio["positions"].items()):
            price_data = prices.get(coin_id)
            if not price_data:
                continue

            current_price = price_data["price"]

            # Check stop loss / take profit
            trigger = check_stop_loss(pos, current_price)
            if trigger:
                result = paper_trading.close_position(
                    coin_id, current_price, trigger,
                )
                if result:
                    self._post_close(result)
                continue

            # Update trailing stop
            updated = update_trailing_stop(pos, current_price)
            if updated["stop_loss"] != pos["stop_loss"]:
                paper_trading.update_stop_loss(coin_id, updated["stop_loss"])

    def _execute_buy(self, signal, indicators, prices: dict):
        """Execute a BUY signal — calculate position and open paper trade."""
        portfolio = paper_trading.load_portfolio()
        portfolio_value = paper_trading.get_portfolio_value(prices)

        # Calculate position size through risk management
        position = calculate_position(
            signal=signal,
            portfolio_value=portfolio_value,
            open_positions=portfolio["positions"],
        )

        if not position.approved:
            self.log.info(
                "Trade rejected for %s: %s",
                signal.symbol, position.rejection_reason,
            )
            return

        # Open the paper trade
        result = paper_trading.open_position(
            coin_id=signal.coin_id,
            symbol=signal.symbol,
            side="long",
            quantity=position.quantity,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            atr=indicators.atr_14 or 0,
            reasons=signal.reasons,
        )

        if result:
            emoji = SIGNAL_EMOJI[signal.signal]
            reasons_str = "\n".join(f"  • {r}" for r in signal.reasons)
            slack.post(TRADE_OPEN_MSG.format(
                side="LONG",
                symbol=signal.symbol,
                emoji=emoji,
                signal=signal.signal.value,
                confidence=signal.confidence,
                entry=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                quantity=position.quantity,
                usd_value=position.usd_value,
                risk_usd=position.risk_usd,
                risk_pct=position.risk_pct,
                reasons=reasons_str,
            ))

    def _post_close(self, trade: dict):
        """Post trade close notification to Slack."""
        pnl = trade["pnl"]
        slack.post(TRADE_CLOSE_MSG.format(
            symbol=trade["symbol"],
            reason=trade["reason"].upper().replace("_", " "),
            entry=trade["entry_price"],
            exit=trade["exit_price"],
            pnl_sign="+" if pnl >= 0 else "-",
            pnl_abs=abs(pnl),
            pnl_pct=trade["pnl_pct"],
            held_since=trade["held_since"],
        ))

    def _post_summary(self, signals, prices: dict):
        """Post the full market scan summary."""
        stats = paper_trading.get_stats()

        signal_lines = []
        for s in sorted(signals, key=lambda x: x.confidence, reverse=True):
            emoji = SIGNAL_EMOJI[s.signal]
            price = prices.get(s.coin_id, {}).get("price", 0)
            change = prices.get(s.coin_id, {}).get("change_24h", 0) or 0
            change_str = f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"
            signal_lines.append(
                f"{emoji} *{s.symbol}* ${price:,.2f} ({change_str}) — "
                f"{s.signal.value} ({s.confidence:.0%})"
            )

        pnl = stats["total_pnl"]
        slack.post(SCAN_SUMMARY_MSG.format(
            signals="\n".join(signal_lines),
            cash=stats["cash"],
            open_positions=stats["open_positions"],
            total_trades=stats["total_trades"],
            win_rate=stats["win_rate"],
            pnl_sign="+" if pnl >= 0 else "-",
            pnl_abs=abs(pnl),
            starting_balance=settings.crypto_paper_balance,
        ))
