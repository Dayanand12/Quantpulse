"""Port: the engine that turns raw ticks into computed market state.

`ITradingEngine` is deliberately narrow — it processes ticks and exposes the
resulting snapshot. It says nothing about how indicators are computed or
which broker the ticks came from; today's adapter delegates to the existing,
already-tested live/live_engine.py::LiveEngine.
"""

from abc import ABC, abstractmethod
from typing import Dict

from core.domain.models import MarketSnapshot, Tick


class ITradingEngine(ABC):
    @abstractmethod
    def process_tick(self, symbol: str, tick: Tick) -> None:
        """Feed one raw tick into the engine."""

    @abstractmethod
    def get_snapshot(self) -> Dict[str, MarketSnapshot]:
        """Return the latest computed snapshot for every tracked symbol."""
