"""IOrderRepository/ITradeRepository implemented over the existing PaperBroker.

live/paper_broker.py's enter()/exit()/positions/trade_log remain the
accounting source of truth (only extended with an optional
initial_stop_loss field for R-multiple metrics — capital/PnL math
untouched). This adapter translates to/from domain types and publishes
PositionOpened/PositionClosed so other modules (a future Trade Journal,
Analytics, or Alerts module) can react without this class, or PaperBroker,
knowing they exist.
"""

import dataclasses
from typing import List, Optional

from core.application.interfaces.charge_config_repository import IChargeConfigRepository
from core.application.interfaces.event_bus import IEventBus
from core.application.interfaces.order_repository import IOrderRepository, ITradeRepository
from core.domain.charges import compute_charges
from core.domain.enums import OrderSide
from core.domain.events import PositionClosed, PositionOpened
from core.domain.models import Position, Trade
from infrastructure.trading.mappers import position_from_raw, trade_from_raw
from runners.paper_trading.paper_broker import PaperBroker


class PaperOrderRepository(IOrderRepository, ITradeRepository):
    def __init__(
        self,
        broker: PaperBroker,
        event_bus: IEventBus,
        deployment_id: Optional[str] = None,
        strategy_name: Optional[str] = None,
        charge_config_repository: Optional[IChargeConfigRepository] = None,
    ) -> None:
        self._broker = broker
        self._event_bus = event_bus
        self._deployment_id = deployment_id
        self._strategy_name = strategy_name
        self._charge_config_repository = charge_config_repository

    def open_position(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        quantity: int,
        market_snapshot: Optional[dict] = None,
    ) -> bool:
        entered = self._broker.enter(symbol, side.value, price, quantity, market_snapshot=market_snapshot)
        if entered:
            position = Position(symbol=symbol, side=side, quantity=quantity, entry_price=price)
            self._event_bus.publish(PositionOpened(position=position))
        return entered

    def close_position(
        self, symbol: str, price: float, initial_stop_loss: Optional[float] = None
    ) -> Optional[Trade]:
        trades_before = len(self._broker.trade_log)
        self._broker.exit(symbol, price, initial_stop_loss=initial_stop_loss)

        if len(self._broker.trade_log) == trades_before:
            return None  # symbol had no open position; PaperBroker no-op'd

        trade = trade_from_raw(self._broker.trade_log[-1])

        charges = None
        net_pnl = None
        if self._charge_config_repository is not None:
            breakdown = compute_charges(
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                quantity=trade.quantity,
                side=trade.side,
                config=self._charge_config_repository.get_config(),
            )
            charges = breakdown.total
            net_pnl = trade.pnl - charges

        trade = dataclasses.replace(
            trade,
            deployment_id=self._deployment_id,
            strategy_name=self._strategy_name,
            charges=charges,
            net_pnl=net_pnl,
        )
        self._event_bus.publish(PositionClosed(trade=trade))
        return trade

    def get_open_position(self, symbol: str) -> Optional[Position]:
        raw = self._broker.positions.get(symbol)
        return position_from_raw(symbol, raw) if raw else None

    def get_open_positions(self) -> List[Position]:
        return [position_from_raw(s, raw) for s, raw in self._broker.positions.items()]

    def get_all(self) -> List[Trade]:
        return [trade_from_raw(raw) for raw in self._broker.trade_log]
