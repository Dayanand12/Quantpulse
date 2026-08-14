"""IWatchlistRepository implemented over SQLAlchemy."""

from datetime import datetime
from typing import List

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from core.application.interfaces.watchlist_repository import IWatchlistRepository
from core.domain.models import Watchlist
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import WatchlistRecord, WatchlistSymbolRecord


def _to_domain(record: WatchlistRecord, symbols: List[str]) -> Watchlist:
    return Watchlist(id=record.id, name=record.name, symbols=tuple(symbols))


class SqlWatchlistRepository(IWatchlistRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def list_watchlists(self) -> List[Watchlist]:
        with unit_of_work(self._session_factory) as session:
            records = session.scalars(select(WatchlistRecord).order_by(WatchlistRecord.id)).all()
            result = []
            for record in records:
                symbols = session.scalars(
                    select(WatchlistSymbolRecord.symbol)
                    .where(WatchlistSymbolRecord.watchlist_id == record.id)
                    .order_by(WatchlistSymbolRecord.id)
                ).all()
                result.append(_to_domain(record, list(symbols)))
            return result

    def create_watchlist(self, name: str) -> Watchlist:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Watchlist name cannot be empty.")

        with unit_of_work(self._session_factory) as session:
            existing = session.scalar(select(WatchlistRecord).where(WatchlistRecord.name == cleaned))
            if existing is not None:
                raise ValueError(f"A watchlist named {cleaned!r} already exists.")

            record = WatchlistRecord(name=cleaned, created_at=datetime.now())
            session.add(record)
            session.flush()
            return _to_domain(record, [])

    def rename_watchlist(self, watchlist_id: int, name: str) -> Watchlist:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Watchlist name cannot be empty.")

        with unit_of_work(self._session_factory) as session:
            record = session.get(WatchlistRecord, watchlist_id)
            if record is None:
                raise ValueError(f"Unknown watchlist: {watchlist_id}")

            conflict = session.scalar(
                select(WatchlistRecord).where(
                    WatchlistRecord.name == cleaned, WatchlistRecord.id != watchlist_id
                )
            )
            if conflict is not None:
                raise ValueError(f"A watchlist named {cleaned!r} already exists.")

            record.name = cleaned
            session.flush()
            symbols = session.scalars(
                select(WatchlistSymbolRecord.symbol)
                .where(WatchlistSymbolRecord.watchlist_id == watchlist_id)
                .order_by(WatchlistSymbolRecord.id)
            ).all()
            return _to_domain(record, list(symbols))

    def delete_watchlist(self, watchlist_id: int) -> None:
        with unit_of_work(self._session_factory) as session:
            record = session.get(WatchlistRecord, watchlist_id)
            if record is None:
                raise ValueError(f"Unknown watchlist: {watchlist_id}")

            total = session.scalar(select(func.count()).select_from(WatchlistRecord))
            if total is not None and total <= 1:
                raise ValueError("Can't delete the only remaining watchlist.")

            session.query(WatchlistSymbolRecord).filter(
                WatchlistSymbolRecord.watchlist_id == watchlist_id
            ).delete()
            session.delete(record)

    def get_symbols(self, watchlist_id: int) -> List[str]:
        with unit_of_work(self._session_factory) as session:
            rows = session.scalars(
                select(WatchlistSymbolRecord.symbol)
                .where(WatchlistSymbolRecord.watchlist_id == watchlist_id)
                .order_by(WatchlistSymbolRecord.id)
            )
            return list(rows)

    def save_symbols(self, watchlist_id: int, symbols: List[str]) -> Watchlist:
        cleaned = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))

        with unit_of_work(self._session_factory) as session:
            record = session.get(WatchlistRecord, watchlist_id)
            if record is None:
                raise ValueError(f"Unknown watchlist: {watchlist_id}")

            session.query(WatchlistSymbolRecord).filter(
                WatchlistSymbolRecord.watchlist_id == watchlist_id
            ).delete()
            session.add_all(
                WatchlistSymbolRecord(watchlist_id=watchlist_id, symbol=s) for s in cleaned
            )
            return _to_domain(record, cleaned)

    def get_all_symbols(self) -> List[str]:
        with unit_of_work(self._session_factory) as session:
            rows = session.scalars(
                select(WatchlistSymbolRecord.symbol).order_by(WatchlistSymbolRecord.id)
            )
            return list(dict.fromkeys(rows))
