"""IWatchlistRepository implemented over SQLAlchemy."""

from typing import List

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.application.interfaces.watchlist_repository import IWatchlistRepository
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import WatchlistSymbolRecord


class SqlWatchlistRepository(IWatchlistRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def get_symbols(self) -> List[str]:
        with unit_of_work(self._session_factory) as session:
            rows = session.scalars(
                select(WatchlistSymbolRecord).order_by(WatchlistSymbolRecord.id)
            )
            return [row.symbol for row in rows]

    def save_symbols(self, symbols: List[str]) -> None:
        cleaned = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))

        with unit_of_work(self._session_factory) as session:
            session.query(WatchlistSymbolRecord).delete()
            session.add_all(WatchlistSymbolRecord(symbol=s) for s in cleaned)
