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
runners/backtesting/): the first-pass config (volume_ratio_min=1.5,
adx_min=22, default 0.1% trailing) massively overtraded — 33,018 trades,
profit factor 0.54, gross P&L +₹448,413 wiped out by ₹1,631,613 in
charges alone (net -₹1,183,200). Tightening adx_min to 30 and
volume_ratio_min to 2.0 cut trades to 12,192 but only improved profit
factor to 0.61 (still a net loser) — the entry filter alone wasn't the
real problem. Widening trailing_pct from the default 0.1% to 1.0%
(StrategyConfig, separate from this file — same fix vwap_reclaim.py
needed) was what actually turned it around: 11,604 trades, 51.5% win
rate, profit factor 1.19, net +₹618,999, Sharpe 1.38. Re-validate with
run_backtest.py before changing adx_min/volume_ratio_min again — and set
trailing_pct=1.0 (not the 0.1% default) if this is ever deployed.
"""

from pathlib import Path
from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide
from core.domain.strategy_conditions import ConditionSet


class OrbBreakoutLongStrategy(IStrategy):
    name = "orb_breakout_long"
    display_name = "ORB Breakout (Long)"
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
