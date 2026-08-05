"""IRegimeCallRepository implemented over SQLAlchemy."""

from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from core.application.interfaces.regime_call_repository import (
    Horizon,
    IRegimeCallRepository,
    PendingEvaluation,
    RegimeCall,
    WinRateStat,
)
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import RegimeCallRecord

_HORIZON_MINUTES: Dict[Horizon, int] = {"15m": 15, "30m": 30, "60m": 60}


def _return_column(record_cls, horizon: Horizon):
    return getattr(record_cls, f"return_{horizon}")


class SqlRegimeCallRepository(IRegimeCallRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def log_call(self, call: RegimeCall) -> None:
        with unit_of_work(self._session_factory) as session:
            exists = session.scalar(
                select(RegimeCallRecord.id).where(
                    RegimeCallRecord.symbol == call.symbol,
                    RegimeCallRecord.logged_at == call.logged_at,
                )
            )
            if exists is not None:
                return

            session.add(RegimeCallRecord(
                symbol=call.symbol,
                logged_at=call.logged_at,
                ltp=call.ltp,
                regime=call.regime,
                trend_strength=call.trend_strength,
                volatility_state=call.volatility_state,
                confidence_score=call.confidence_score,
                decision=call.decision,
                suggested_side=call.suggested_side,
            ))
            try:
                session.flush()
            except IntegrityError:
                # Two concurrent pollers both passed the exists-check for
                # the same (symbol, logged_at) before either committed —
                # the unique constraint caught the race, drop this insert.
                session.rollback()

    def win_rate(self, symbol: str, decision: str, horizon: Horizon, since: datetime) -> WinRateStat:
        column = _return_column(RegimeCallRecord, horizon)
        with unit_of_work(self._session_factory) as session:
            rows = session.scalars(
                select(RegimeCallRecord).where(
                    RegimeCallRecord.symbol == symbol,
                    RegimeCallRecord.decision == decision,
                    RegimeCallRecord.logged_at >= since,
                    column.isnot(None),
                )
            ).all()

            wins = 0
            for row in rows:
                pct_return = getattr(row, f"return_{horizon}")
                won = pct_return > 0 if row.suggested_side == "BUY" else pct_return < 0
                wins += int(won)

        n = len(rows)
        return WinRateStat(win_rate=(wins / n * 100) if n else 0.0, wins=wins, n=n)

    def pending_evaluations(self, horizon: Horizon, now: datetime) -> List[PendingEvaluation]:
        column = _return_column(RegimeCallRecord, horizon)
        cutoff = now - timedelta(minutes=_HORIZON_MINUTES[horizon])

        with unit_of_work(self._session_factory) as session:
            rows = session.scalars(
                select(RegimeCallRecord).where(
                    RegimeCallRecord.logged_at <= cutoff,
                    column.is_(None),
                )
            ).all()
            return [
                PendingEvaluation(
                    id=row.id,
                    symbol=row.symbol,
                    logged_at=row.logged_at,
                    ltp=row.ltp,
                    suggested_side=row.suggested_side,
                )
                for row in rows
            ]

    def record_return(self, call_id: int, horizon: Horizon, pct_return: float) -> None:
        with unit_of_work(self._session_factory) as session:
            record = session.get(RegimeCallRecord, call_id)
            if record is not None:
                setattr(record, f"return_{horizon}", pct_return)
