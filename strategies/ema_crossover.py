"""EMA 5/9 Crossover (Long) — simple test strategy.

Deliberately minimal: enter long the moment the 5 EMA crosses above the
9 EMA. Both are already computed by live/live_engine.py (added ema5
alongside the existing ema9/ema21) and passed through untouched in
snapshot[symbol]. Exit is handled entirely by the universal SL/target/
trailing machinery in live/execution_manager.py, same as every other
strategy — nothing here decides when to exit.

Tracks each symbol's previous EMA reading on the instance (the registry
keeps one instance alive for the process's lifetime) so screen() fires
only on the crossing tick itself, not on every tick where ema5 happens to
already be above ema9.
"""

from typing import Dict, List, Optional, Tuple

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide


class EmaCrossoverStrategy(IStrategy):
    name = "ema_crossover"
    display_name = "EMA 5/9 Crossover (Long)"
    side = OrderSide.BUY

    def __init__(self) -> None:
        self._previous: Dict[str, Tuple[float, float]] = {}

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        candidates = []

        for symbol in symbols:
            data = snapshot.get(symbol)
            if not data:
                continue

            ema5 = data.get("ema5")
            ema9 = data.get("ema9")
            if ema5 is None or ema9 is None:
                continue

            previous = self._previous.get(symbol)
            self._previous[symbol] = (ema5, ema9)
            if previous is None:
                continue

            prev_ema5, prev_ema9 = previous
            crossed_up = prev_ema5 <= prev_ema9 and ema5 > ema9
            if crossed_up:
                candidates.append(symbol)

        return candidates
