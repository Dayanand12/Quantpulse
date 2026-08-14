"""Port: a source of raw live ticks (NOT computed indicators — that's
ITradingEngine's job; this port only answers "what did the market just do").

Today's only adapter wraps the Zerodha WebSocket client. A future adapter
(a different broker, a second exchange, a replay-from-disk provider for
backtesting) implements this same interface — nothing above this seam has
to know or care which one is in use.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from core.domain.models import Tick


class IMarketDataProvider(ABC):
    @abstractmethod
    def start(self, symbols: List[str]) -> None:
        """Begin streaming ticks for the given symbols."""

    @abstractmethod
    def get_latest_ticks(self) -> Dict[str, Tick]:
        """Return the most recent raw tick received for every subscribed symbol."""

    @abstractmethod
    def add_symbol(self, symbol: str) -> None:
        """Subscribe one more symbol on an already-running feed — no
        restart needed. A no-op if already subscribed."""

    @abstractmethod
    def seconds_since_last_tick(self) -> Optional[float]:
        """How long since a tick actually arrived, or None if none has yet.
        The feed-health signal — market_data can hold stale values forever
        after a dead websocket, so this has to come from callback activity,
        not from whether get_latest_ticks() returns anything."""
