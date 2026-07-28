"""Ports: read/write access to orders, positions, and trades.

Business logic (execution, risk, portfolio, journal, analytics) depends only
on these interfaces. Today's adapter is in-memory, backed by the existing
live/paper_broker.py::PaperBroker. A future SQL-backed implementation
(infrastructure/persistence) swaps in without any caller changing — that's
the entire point of the repository pattern.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from core.domain.enums import OrderSide
from core.domain.models import Position, Trade


class IOrderRepository(ABC):
    @abstractmethod
    def open_position(self, symbol: str, side: OrderSide, price: float, quantity: int) -> bool:
        """Attempt to open a position. Returns False if rejected (e.g. capital)."""

    @abstractmethod
    def close_position(
        self, symbol: str, price: float, initial_stop_loss: Optional[float] = None
    ) -> Optional[Trade]:
        """Close an open position at the given price. Returns the resulting
        Trade. `initial_stop_loss` (the SL set at entry, if the caller
        tracked one) is attached to the Trade for R-multiple calculation —
        optional and backward compatible; omit it and the Trade simply
        won't contribute to average R-multiple."""

    @abstractmethod
    def get_open_position(self, symbol: str) -> Optional[Position]:
        """Return the open position for a symbol, if any."""

    @abstractmethod
    def get_open_positions(self) -> List[Position]:
        """Return every currently open position."""


class ITradeRepository(ABC):
    @abstractmethod
    def get_all(self) -> List[Trade]:
        """Return the full trade history, oldest first."""
