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
run_backtest.py before changing adx_threshold again.

The actual thresholds/conditions (volume_ratio_threshold, adx_threshold,
the VWAP-reclaim crossing, ema9 > ema21) live in vwap_reclaim.json next to
this file, not here — see core/domain/strategy_conditions.py. Edit that
JSON to tune this strategy; nothing in this .py file needs to change for
a threshold tweak.
"""

from pathlib import Path
from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide
from core.domain.strategy_conditions import ConditionSet


class VwapReclaimStrategy(IStrategy):
    name = "vwap_reclaim_long_v1"
    display_name = "VWAP Reclaim (Long) [vwap_reclaim_long_v1]"
    side = OrderSide.BUY

    def __init__(self) -> None:
        self._conditions = ConditionSet.from_file(Path(__file__).with_suffix(".json"))

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        candidates = []

        for symbol in symbols:
            data = snapshot.get(symbol)
            if not data:
                continue

            if self._conditions.evaluate(symbol, data):
                candidates.append(symbol)

        return candidates
