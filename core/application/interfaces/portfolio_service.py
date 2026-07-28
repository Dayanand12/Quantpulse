"""Port: the current state of the trading account.

Deliberately separate from IOrderRepository — portfolio is a read-oriented
view (capital, exposure, P&L) that a future multi-strategy or multi-broker
setup will need to aggregate across several order repositories. Keeping it
as its own interface means that aggregation can be added later without
touching order/position/trade storage.
"""

from abc import ABC, abstractmethod

from core.domain.models import PortfolioSnapshot


class IPortfolioService(ABC):
    @abstractmethod
    def get_status(self) -> PortfolioSnapshot:
        """Return the current portfolio snapshot."""
