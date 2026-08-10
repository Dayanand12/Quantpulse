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

from core.domain.enums import OrderSide
from core.domain.json_condition_strategy import JsonConditionStrategy


class VwapReclaimStrategy(JsonConditionStrategy):
    name = "vwap_reclaim"
    display_name = "VWAP Reclaim (Long)"
    side = OrderSide.BUY
