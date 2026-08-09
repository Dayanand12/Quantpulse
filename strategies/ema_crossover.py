"""EMA 5/9 Crossover (Long) — simple test strategy.

Deliberately minimal: enter long the moment the 5 EMA crosses above the
9 EMA. Both are already computed by live/live_engine.py (added ema5
alongside the existing ema9/ema21) and passed through untouched in
snapshot[symbol]. Exit is handled entirely by the universal SL/target/
trailing machinery in live/execution_manager.py, same as every other
strategy — nothing here decides when to exit.

The crossing condition lives in ema_crossover.json next to this file, not
here — see core/domain/strategy_conditions.py.
"""

from pathlib import Path
from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide
from core.domain.strategy_conditions import ConditionSet


class EmaCrossoverStrategy(IStrategy):
    name = "ema_crossover"
    display_name = "EMA 5/9 Crossover (Long)"
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
