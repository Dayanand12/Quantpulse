"""Test Always Short — deliberately always signals every symbol, SELL side.

Not a real trading strategy. It exists to exercise the paper-trading
pipeline end-to-end (entry -> SL/target/trailing -> exit -> P&L) without
waiting on real market conditions to line up. execution_manager.py already
skips symbols with an open position and respects max_cycles_per_day, so
this just re-enters every symbol as soon as it's flat, up to that cap.

Pairs with test_always_long.py so both BUY-side and SELL-side paper
trading math get covered. Delete both files once you're done verifying.
"""

from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide


class TestAlwaysShortStrategy(IStrategy):
    name = "test_always_short"
    display_name = "TEST: Always Short"
    side = OrderSide.SELL

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        return [symbol for symbol in symbols if snapshot.get(symbol)]
