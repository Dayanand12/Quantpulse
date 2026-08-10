# core/domain/json_condition_strategy.py
"""Shared base for every strategy whose entry logic is a conditions.json
file (core/domain/strategy_conditions.py) instead of hand-written boolean
logic — vwap_reclaim.py, rsi_mean_reversion.py, ema_crossover.py,
orb_breakout_long.py, orb_trend_volume_adx_long.py, torb_breakout_long.py,
and torb_breakout_short.py all use this now instead of each duplicating
the same __init__/screen() body. A subclass is just:

    class MyStrategy(JsonConditionStrategy):
        name = "my_strategy"
        display_name = "My Strategy"
        side = OrderSide.BUY

and it loads my_strategy.json (same directory, same basename) automatically.

Accepts an explicit `conditions` override instead of always reading the
file — this is what makes running the same strategy with a temporary,
not-saved-to-disk parameter set possible (see runners/backtesting/
batch_runner.py), without which testing N variants means overwriting the
one real file N times in sequence, one at a time, never in parallel.
"""

import inspect
from pathlib import Path
from typing import Dict, List, Optional

from core.application.interfaces.strategy import IStrategy
from core.domain.strategy_conditions import ConditionSet


class JsonConditionStrategy(IStrategy):
    def __init__(self, conditions: Optional[ConditionSet] = None) -> None:
        self._conditions = conditions or ConditionSet.from_file(self._default_conditions_path())

    def _default_conditions_path(self) -> Path:
        # inspect.getfile resolves correctly regardless of how the class
        # was loaded — a normal `import strategies.<name>` or
        # FileStrategyRegistry's synthetic-module spec loading both set
        # the underlying code object's file path the same way.
        return Path(inspect.getfile(type(self))).with_suffix(".json")

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        candidates = []

        for symbol in symbols:
            data = snapshot.get(symbol)
            if not data:
                continue

            if self._conditions.evaluate(symbol, data):
                candidates.append(symbol)

        return candidates
