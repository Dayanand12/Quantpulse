"""Persists every closed trade to the `trades` table.

Subscribes to PositionClosed on the shared event bus — this is the "future
Trade Journal... plugs in by adding a subscriber" hook core/domain/events.py
was written for. Neither PaperBroker nor ExecutionManager know this class
exists; wiring is entirely in core/container.py.

Runs on the publisher's thread (InProcessEventBus calls handlers
synchronously — see its docstring), so this stays to one INSERT and never
raises: a journal failure must never interrupt live trading.
"""

from sqlalchemy.orm import sessionmaker

from core.application.interfaces.event_bus import IEventBus
from core.domain.events import PositionClosed
from infrastructure.logging.logger import get_logger
from infrastructure.persistence.models import TradeRecord

logger = get_logger(__name__)


class SqlTradeJournal:
    def __init__(self, session_factory: sessionmaker, event_bus: IEventBus) -> None:
        self._session_factory = session_factory
        event_bus.subscribe(PositionClosed, self._on_position_closed)

    def _on_position_closed(self, event: PositionClosed) -> None:
        trade = event.trade
        try:
            session = self._session_factory()
            try:
                session.add(
                    TradeRecord(
                        symbol=trade.symbol,
                        side=trade.side.value,
                        quantity=trade.quantity,
                        entry_price=trade.entry_price,
                        exit_price=trade.exit_price,
                        pnl=trade.pnl,
                        closed_at=trade.closed_at,
                        opened_at=trade.opened_at,
                        initial_stop_loss=trade.initial_stop_loss,
                        deployment_id=trade.deployment_id,
                        strategy_name=trade.strategy_name,
                        entry_rsi=trade.entry_rsi,
                        entry_adx=trade.entry_adx,
                        entry_atr_pct=trade.entry_atr_pct,
                        entry_vwap=trade.entry_vwap,
                        entry_volume_ratio=trade.entry_volume_ratio,
                        market_condition=trade.market_condition,
                        charges=trade.charges,
                        net_pnl=trade.net_pnl,
                    )
                )
                session.commit()
            finally:
                session.close()
        except Exception:
            logger.exception("Failed to persist closed trade for %s", trade.symbol)
