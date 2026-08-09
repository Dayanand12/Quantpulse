"""RSI Oversold Bounce (Long) — Larry Connors-style mean-reversion.

Classic proven intraday approach: don't fight the primary trend, but buy
sharp, short-term pullbacks within it. Requires price above ema21 (the
uptrend filter) AND RSI14 dipping into oversold territory (<=30) and
then turning back up — the pullback-is-over signal — rather than
buying the falling knife the moment RSI crosses below 30. Exit is
handled entirely by the universal SL/target/trailing machinery in
runners/paper_trading/execution_manager.py, same as every other
strategy — nothing here decides when to exit.

The actual threshold/conditions (oversold_rsi, the uptrend filter, the
RSI-turning-up crossing) live in rsi_mean_reversion.json next to this
file, not here — see core/domain/strategy_conditions.py. Edit that JSON
to tune this strategy; nothing in this .py file needs to change for a
threshold tweak.
"""

from pathlib import Path
from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide
from core.domain.strategy_conditions import ConditionSet


class RsiMeanReversionStrategy(IStrategy):
    name = "rsi_mean_reversion"
    display_name = "RSI Oversold Bounce (Long)"
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
