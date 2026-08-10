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

from core.domain.enums import OrderSide
from core.domain.json_condition_strategy import JsonConditionStrategy


class EmaCrossoverStrategy(JsonConditionStrategy):
    name = "ema_crossover"
    display_name = "EMA 5/9 Crossover (Long)"
    side = OrderSide.BUY
