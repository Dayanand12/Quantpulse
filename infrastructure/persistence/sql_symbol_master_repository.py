"""ISymbolMasterRepository implemented over SQLAlchemy."""

from typing import List

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import sessionmaker

from core.application.interfaces.symbol_master_repository import (
    ISymbolMasterRepository,
    SymbolSuggestion,
)
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import NseSymbolRecord


class SqlSymbolMasterRepository(ISymbolMasterRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def search(self, query: str, limit: int = 20) -> List[SymbolSuggestion]:
        cleaned = query.strip().upper()
        if not cleaned:
            return []

        like = f"%{cleaned}%"
        # Symbols starting with the query rank above symbols that merely
        # contain it (typing "REL" should surface RELIANCE before a symbol
        # that happens to contain "REL" mid-string), company-name matches
        # trail behind tradingsymbol matches either way.
        rank = case(
            (NseSymbolRecord.tradingsymbol.like(f"{cleaned}%"), 0),
            (NseSymbolRecord.tradingsymbol.like(like), 1),
            else_=2,
        )

        with unit_of_work(self._session_factory) as session:
            rows = session.execute(
                select(NseSymbolRecord)
                .where(
                    or_(
                        NseSymbolRecord.tradingsymbol.like(like),
                        NseSymbolRecord.name.like(like),
                    )
                )
                .order_by(rank, NseSymbolRecord.tradingsymbol)
                .limit(limit)
            ).scalars()
            return [SymbolSuggestion(r.tradingsymbol, r.name) for r in rows]

    def replace_all(self, symbols: List[SymbolSuggestion]) -> None:
        with unit_of_work(self._session_factory) as session:
            session.query(NseSymbolRecord).delete()
            session.add_all(
                NseSymbolRecord(tradingsymbol=s.tradingsymbol, name=s.name) for s in symbols
            )

    def count(self) -> int:
        with unit_of_work(self._session_factory) as session:
            return session.scalar(select(func.count()).select_from(NseSymbolRecord)) or 0
