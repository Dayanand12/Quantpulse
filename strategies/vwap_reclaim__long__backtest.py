"""VWAP Reclaim (Long) — classic intraday momentum strategy.

Session VWAP is the level intraday desks use to judge whether the
day's flow is net buying or net selling. This strategy waits for price
to cross from below VWAP to above it (a "reclaim") while volume is
running hot (volume_ratio > 1.5x the recent average), the short-term
trend already agrees (ema9 > ema21), and ADX confirms there's an actual
trend to trade (not just noise sitting right at VWAP) — the combination
that separates a genuine breakout from a ranging chop. Exit is handled
entirely by the universal SL/target/trailing machinery in
runners/paper_trading/execution_manager.py, same as every other
strategy — nothing here decides when to exit.

Backtested across the full watchlist, 2024-10 to 2026-08 (22 months,
1-minute bars, see runners/backtesting/): without an ADX gate, most
trades (73%) fired in ranging conditions (ADX < 25) and accounted for
77% of total losses — net -₹609,148 over 9,478 trades, profit factor
0.54. Adding ADX >= 25 alone cut losses to -₹141,165 (2,703 trades,
profit factor 0.65) but didn't reach profitability; the deployment's
trailing_pct (StrategyConfig, separate from this file) also needed
widening from 0.1% to 1.0% — that combination was the first to turn net
positive (+₹220,403, profit factor 1.18). Re-validate with
run_backtest.py before changing ADX_THRESHOLD again.

Tracks each symbol's previous close-vs-VWAP relationship on the
instance (the registry keeps one instance alive for the process's
lifetime) so screen() fires only on the crossing tick itself.
"""

from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide

VOLUME_RATIO_THRESHOLD = 1.5
ADX_THRESHOLD = 25


class VwapReclaimStrategy(IStrategy):
    name = "vwap_reclaim__long__backtest"
    display_name = "VWAP Reclaim (Long) [vwap_reclaim__long__backtest]"
    side = OrderSide.BUY

    def __init__(self) -> None:
        self._was_below: Dict[str, bool] = {}

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        candidates = []

        for symbol in symbols:
            data = snapshot.get(symbol)
            if not data:
                continue

            ltp = data.get("ltp")
            vwap = data.get("vwap")
            ema9 = data.get("ema9")
            ema21 = data.get("ema21")
            volume_ratio = data.get("volume_ratio")
            adx = data.get("adx")
            if None in (ltp, vwap, ema9, ema21, volume_ratio, adx):
                continue

            was_below = self._was_below.get(symbol)
            self._was_below[symbol] = ltp < vwap
            if was_below is None:
                continue

            reclaimed = was_below and ltp >= vwap
            trending_up = ema9 > ema21
            volume_confirmed = volume_ratio >= VOLUME_RATIO_THRESHOLD
            trend_strong = adx >= ADX_THRESHOLD

            if reclaimed and trending_up and volume_confirmed and trend_strong:
                candidates.append(symbol)

        return candidates
