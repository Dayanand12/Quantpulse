"""ITradeRepository implemented over SQLAlchemy.

record_to_trade is the one place TradeRecord -> Trade mapping happens —
backend/eod_report.py imports it from here rather than keeping its own
copy, now that a second caller (analytics) needs the same mapping.
"""

from datetime import datetime, time
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.application.interfaces.trade_repository import ITradeRepository, TradeFilter
from core.domain.enums import OrderSide
from core.domain.models import Trade
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import TradeRecord

# NSE equity session bounds — a date_from/date_to filter means "that
# trading day," not the calendar day, so a single-day range (date_from ==
# date_to) spans exactly market open to market close rather than midnight
# to midnight.
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def record_to_trade(record: TradeRecord) -> Trade:
    return Trade(
        symbol=record.symbol,
        side=OrderSide(record.side),
        quantity=record.quantity,
        entry_price=record.entry_price,
        exit_price=record.exit_price,
        pnl=record.pnl,
        closed_at=record.closed_at,
        opened_at=record.opened_at,
        initial_stop_loss=record.initial_stop_loss,
        deployment_id=record.deployment_id,
        strategy_name=record.strategy_name,
        entry_rsi=record.entry_rsi,
        entry_adx=record.entry_adx,
        entry_atr_pct=record.entry_atr_pct,
        entry_vwap=record.entry_vwap,
        entry_volume_ratio=record.entry_volume_ratio,
        market_condition=record.market_condition,
        charges=record.charges,
        net_pnl=record.net_pnl,
    )


class SqlTradeRepository(ITradeRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def list_trades(self, filters: Optional[TradeFilter] = None) -> List[Trade]:
        filters = filters or TradeFilter()
        stmt = select(TradeRecord).order_by(TradeRecord.closed_at)

        if filters.strategy_name:
            stmt = stmt.where(TradeRecord.strategy_name == filters.strategy_name)
        if filters.deployment_id:
            stmt = stmt.where(TradeRecord.deployment_id == filters.deployment_id)
        if filters.symbol:
            stmt = stmt.where(TradeRecord.symbol == filters.symbol)
        if filters.date_from:
            stmt = stmt.where(
                TradeRecord.closed_at >= datetime.combine(filters.date_from, MARKET_OPEN)
            )
        if filters.date_to:
            stmt = stmt.where(
                TradeRecord.closed_at <= datetime.combine(filters.date_to, MARKET_CLOSE)
            )

        with unit_of_work(self._session_factory) as session:
            records = session.scalars(stmt)
            return [record_to_trade(r) for r in records]
