"""IPortfolioService implemented over the existing PaperBroker."""

from core.application.interfaces.portfolio_service import IPortfolioService
from core.domain.models import PortfolioSnapshot
from infrastructure.trading.mappers import (
    position_from_raw,
    rejected_entry_from_raw,
    trade_from_raw,
)
from runners.paper_trading.paper_broker import PaperBroker


class PaperPortfolioService(IPortfolioService):
    def __init__(self, broker: PaperBroker) -> None:
        self._broker = broker

    def get_status(self) -> PortfolioSnapshot:
        status = self._broker.status()
        return PortfolioSnapshot(
            available_capital=status["available_capital"],
            open_positions=tuple(
                position_from_raw(symbol, raw)
                for symbol, raw in status["open_positions"].items()
            ),
            total_trades=status["total_trades"],
            trade_log=tuple(trade_from_raw(raw) for raw in status["trade_log"]),
            rejected_entries=tuple(
                rejected_entry_from_raw(raw) for raw in status["rejected_entries"].values()
            ),
        )
