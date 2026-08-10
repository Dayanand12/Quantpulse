"""ORB Breakout (Long) — classic opening-range-breakout momentum entry.

Different in kind from orb_reversal.py: that strategy trades a rejection
NEAR the opening-range low (short bias); this one trades a genuine
breakout ABOVE the opening-range high (long bias) — the more commonly
documented ORB pattern (enter when price actually clears the first
15-minute range, in the direction of the break, with volume/trend
confirmation to filter false breakouts in a ranging market).

Built as a fresh strategy file rather than a literal clone of
orb_reversal.py: that file's stage1/2/3 funnel is shared with
services/filter_engine.py's Screener-page display loop, which has no
bearing on a breakout strategy — this one only needs the same
conditions.json pattern vwap_reclaim.py/rsi_mean_reversion.py already use.

orb_high (core/domain/strategy_conditions.py's VALID_SNAPSHOT_FIELDS) is
masked to None until the 9:15-9:30 opening range has actually finished
forming, so this can never fire on a still-forming range — the entry
condition literally requires the range to already be locked in.

Backtested across the full watchlist, whole available history (see
runners/backtesting/), starting from the same base as orb_breakout_long
(adx_min=30, volume_ratio_min=2.0, trailing_pct=1.0 — see that file's
docstring for why the entry filter alone and the default 0.1% trailing
both needed fixing first): 11,604 trades, 51.5% win rate, profit factor
1.19, net +₹618,999, Sharpe 1.38.

Breaking winners vs losers down by entry-time indicator value: entry_adx,
entry_volume_ratio, entry_atr_pct, entry_rsi means were statistically
indistinguishable between winners and losers (no signal), and
market_condition didn't help either (99.8% of trades share the identical
label, since the entry conditions already guarantee "Trending / High
Volume / Above VWAP"). Bucketing by entry ADX in 5-point bands did show a
real pattern: every bucket from 30-60 was profitable, but EVERY bucket
from 60 upward lost money (ADX 60-65: -₹21,389 at 50.0% win rate; 65-70:
-₹10,623 at 46.9%; 70-75: -₹5,949 at 43.2%; 75-80: -₹1,242 at 28.0%) —
consistent across 5 buckets, not one outlier. Matches real market
behavior: ADX that high usually means the move is already extended by
the time price clears the opening range, not a fresh breakout with room
to run. Added adx_max=60 to exclude these — re-validated: 11,307 trades
(only ~300 fewer), win rate 51.7%, profit factor 1.21, net +₹659,879,
max drawdown down to ₹67,702 (from ₹74,713), Sharpe 1.48. Every metric
improved together from removing under 3% of trades — re-validate with
run_backtest.py before loosening adx_max again, and set trailing_pct=1.0
(not the 0.1% default) if this is ever deployed.
"""

from core.domain.enums import OrderSide
from core.domain.json_condition_strategy import JsonConditionStrategy


class OrbBreakoutLongStrategy(JsonConditionStrategy):
    name = "orb_trend_volume_adx_long"
    display_name = "ORB Trend + Volume + ADX (Long)"
    side = OrderSide.BUY
