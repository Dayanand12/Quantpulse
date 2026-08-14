"""ORB Trend + Volume + ADX (Long), with a broader-market regime filter —
a clone of orb_trend_volume_adx_long.py with exactly one condition added:
NIFTY 50's own EMA9 > EMA21 (see the nifty_ema9/nifty_ema21 snapshot
fields, core/domain/strategy_conditions.py's VALID_SNAPSHOT_FIELDS). The
idea: only take this stock's breakout while the broader market is itself
in an uptrend, instead of trading a stock-level signal in isolation.

Needs runners/backtesting/engine.py's NIFTY regime join (added alongside
this file) — backtest-only for now, not yet wired into live/paper trading
(runners/paper_trading/live_engine.py doesn't compute nifty_* fields), so
this can be researched/tuned here first before ever being deployed live.

Unvalidated as of creation — no backtest run yet. Re-run against the
original (no regime filter) before trusting this variant over it; the
regime condition can only ever reduce trade count relative to the
original (it's ANDed onto the same conditions, never a substitute for
any of them), so compare trade count / win rate / profit factor side by
side, not just look at this one in isolation.
"""

from core.domain.enums import OrderSide
from core.domain.json_condition_strategy import JsonConditionStrategy


class OrbBreakoutLongRegimeStrategy(JsonConditionStrategy):
    name = "orb_trend_volume_adx_long_regime"
    display_name = "ORB Trend + Volume + ADX + Regime (Long) [orb_trend_volume_adx_long_regime]"
    side = OrderSide.BUY
