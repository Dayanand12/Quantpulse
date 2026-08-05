"""ORB Reversal (Short) — the strategy that's been running since day one.

This is the pattern for any new strategy file dropped into strategies/:
a class implementing core.application.interfaces.strategy.IStrategy, with
a unique `name` and a `screen()` that returns which of the given symbols
it wants to enter right now. Risk/sizing (quantity, SL%, target%,
trailing%, max cycles/day) is NOT this class's job — that's universal,
set per-deployment, and applied by live/execution_manager.py the same way
for every strategy.

screen() reuses backend/filter_engine.py's stage1/2/3 filters unchanged —
same thresholds, same tested logic, just called here instead of (also) in
that module's standalone display loop.
"""

from typing import Dict, List

from services.filter_engine import stage1_filter, stage2_filter, stage3_filter
from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide


class ORBReversalStrategy(IStrategy):
    name = "orb_reversal"
    display_name = "ORB Reversal (Short)"
    side = OrderSide.SELL

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        ranked = []

        for symbol in symbols:
            data = snapshot.get(symbol)
            if not data:
                continue

            if stage1_filter(data) and stage2_filter(data) and stage3_filter(data):
                ranked.append((symbol, data.get("volume_ratio") or 0))

        ranked.sort(key=lambda pair: pair[1], reverse=True)
        return [symbol for symbol, _ in ranked[:5]]
