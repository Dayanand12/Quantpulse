"""TORB (Timely Opening Range Breakout) — Short, pure signal, no filters.

Mirror of torb_breakout_long.py: support = low of the observed opening
period; sell (short) the moment price crosses below it. See that file's
docstring for the paper this is adapted from and the two deliberate
departures from it (exit model, fixed vs. tunable observation window).

Backtested across the full watchlist, whole available history: default
0.1% trailing overtrades the same way the long side does — 66,930+
trades range, profit factor 0.44, net -₹6,514,762 (charges ₹7,387,967
against gross +₹873,206). Widening trailing_pct to 1.0% turns it net
positive but only marginally: 66,930 trades, 49.0% win rate, profit
factor 1.05, net +₹894,821, Sharpe 0.53 — notably weaker than
torb_breakout_long.py's 1.12 profit factor / 1.48 Sharpe on the same
fix. The short side of this pure breakout has real but much thinner
edge on NSE cash equities; don't assume symmetry with the long side.
"""

from core.domain.enums import OrderSide
from core.domain.json_condition_strategy import JsonConditionStrategy


class TorbBreakoutShortStrategy(JsonConditionStrategy):
    name = "torb_breakout_short"
    display_name = "TORB Breakdown (Short, no filters)"
    side = OrderSide.SELL
