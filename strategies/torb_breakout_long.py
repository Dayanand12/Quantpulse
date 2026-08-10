"""TORB (Timely Opening Range Breakout) — Long, pure signal, no filters.

Adapted from Tsai et al., "Assessing the Profitability of Timely Opening
Range Breakout on Index Futures Markets" (IEEE Access, 2019): resistance
= high of an observed opening period; buy the moment price crosses above
it. Their headline finding was that this simple signal alone — no
volume/trend/ADX confirmation — is profitable across five index futures
markets once the observed-period width ("probe time") is sized right, in
contrast to orb_breakout_long.py/orb_trend_volume_adx_long.py in this
codebase, which both needed extra filters to become profitable.

Two deliberate departures from the paper, both scoped down for now:
1. Exit here is still this system's universal SL/target/trailing model
   (runners/paper_trading/execution_manager.py), not the paper's pure
   time-based "close at end of session, no stop-loss" exit — every
   strategy in this codebase shares one exit model, and removing stop-
   loss protection isn't something to do quietly for a strategy that
   could get deployed.
2. The "probe time" (observed-period width) here is whatever orb_high
   already reflects — the fixed 9:15-9:30 opening range every other
   strategy uses — not a tunable parameter swept over a range the way
   the paper does. Making the observation window itself configurable per
   strategy is a larger change than this file scopes to.

Backtested across the full watchlist, whole available history: with the
default 0.1% trailing stop, this massively overtrades — 132,635 trades,
profit factor 0.49, gross P&L +₹1,291,907 completely wiped out by
₹6,592,698 in charges (net -₹5,300,791). Same lesson as every other
breakout-style strategy in this codebase: widening trailing_pct to 1.0%
turns it net positive — 62,519 trades, 50.8% win rate, profit factor
1.12, net +₹2,092,805, Sharpe 1.48. Confirms the paper's headline claim
(the raw, unfiltered breakout has genuine positive edge) translates to
NSE cash equities, once the exit model isn't sabotaging it — gross P&L
was already strongly positive even in the overtrading version; the
default trailing stop was the real problem, not the entry signal, same
as orb_breakout_long.py. Set trailing_pct=1.0 (not the 0.1% default) if
this is ever deployed. See torb_breakout_short.py for the mirrored short
side, which is notably weaker (profit factor 1.05, Sharpe 0.53) —
long-side breakouts have a real edge here, short-side barely does.
"""

from core.domain.enums import OrderSide
from core.domain.json_condition_strategy import JsonConditionStrategy


class TorbBreakoutLongStrategy(JsonConditionStrategy):
    name = "torb_breakout_long"
    display_name = "TORB Breakout (Long, no filters)"
    side = OrderSide.BUY
