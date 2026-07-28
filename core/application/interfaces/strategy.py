"""Port: one strategy's signal logic.

Deliberately narrow — a strategy only decides WHICH symbols to enter and
in WHICH direction. Risk/sizing (quantity, SL/target/trailing %, max
cycles) is universal and lives on StrategyConfig instead, applied by
live/execution_manager.py the same way regardless of which strategy is
running.

`screen()` operates on the same raw dict snapshot shape
LiveEngine.get_snapshot() returns (symbol -> {"ltp":..., "vwap":..., ...}),
not the domain MarketSnapshot the API layer uses. That's a deliberate,
pragmatic choice: it lets strategies call backend/filter_engine.py's
existing tested filter functions directly, with no conversion layer
between the engine's native shape and strategy code.
"""

from abc import ABC, abstractmethod
from typing import Dict, List

from core.domain.enums import OrderSide


class IStrategy(ABC):
    name: str
    display_name: str
    side: OrderSide

    @abstractmethod
    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        """Return the subset of `symbols` this strategy wants to enter now."""
