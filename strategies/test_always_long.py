"""Test Always Long — deliberately always signals every symbol, BUY side.

Not a real trading strategy. It exists to exercise the paper-trading
pipeline end-to-end (entry -> SL/target/trailing -> exit -> P&L) without
waiting on real market conditions to line up. execution_manager.py already
skips symbols with an open position and respects max_cycles_per_day, so
this just re-enters every symbol as soon as it's flat, up to that cap.

Delete this file once you're done verifying paper trading works.
"""

from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide


class TestAlwaysLongStrategy(IStrategy):
    name = "test_always_long"
    display_name = "TEST: Always Long"
    side = OrderSide.BUY

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        return [symbol for symbol in symbols if snapshot.get(symbol)]
