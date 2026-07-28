"""Port: a source of raw live ticks (NOT computed indicators — that's
ITradingEngine's job; this port only answers "what did the market just do").

Today's only adapter wraps the Zerodha WebSocket client. A future adapter
(a different broker, a second exchange, a replay-from-disk provider for
backtesting) implements this same interface — nothing above this seam has
to know or care which one is in use.
"""

from abc import ABC, abstractmethod
from typing import Dict, List

from core.domain.models import Tick


class IMarketDataProvider(ABC):
    @abstractmethod
    def start(self, symbols: List[str]) -> None:
        """Begin streaming ticks for the given symbols."""

    @abstractmethod
    def get_latest_ticks(self) -> Dict[str, Tick]:
        """Return the most recent raw tick received for every subscribed symbol."""
