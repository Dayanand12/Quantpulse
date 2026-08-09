"""IBacktestResultRepository implemented over SQLAlchemy. save_result()
upserts on the identity fields (see models.py::BacktestResultRecord's
unique constraint) instead of a plain insert, so re-running a backtest
with parameters identical to a previously stored run refreshes that row
rather than creating a duplicate.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.application.interfaces.backtest_result_repository import IBacktestResultRepository
from core.domain.backtest_result import BacktestResult, BacktestRunParams
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import BacktestResultRecord


def _record_to_result(record: BacktestResultRecord) -> BacktestResult:
    params = BacktestRunParams(
        strategy_name=record.strategy_name,
        symbols=record.symbols,
        timeframe=record.timeframe,
        date_from=record.date_from,
        date_to=record.date_to,
        quantity=record.quantity,
        stoploss_pct=record.stoploss_pct,
        target_pct=record.target_pct,
        trailing_pct=record.trailing_pct,
        max_cycles_per_day=record.max_cycles_per_day,
        start_time=record.start_time,
        end_time=record.end_time,
        charges_enabled=record.charges_enabled,
        strategy_params_json=record.strategy_params_json,
    )
    return BacktestResult(
        id=record.id,
        params=params,
        result=json.loads(record.result_json),
        created_at=record.created_at,
    )


class SqlBacktestResultRepository(IBacktestResultRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def save_result(self, params: BacktestRunParams, result: Dict[str, Any]) -> BacktestResult:
        with unit_of_work(self._session_factory) as session:
            existing = session.execute(
                select(BacktestResultRecord).where(
                    BacktestResultRecord.strategy_name == params.strategy_name,
                    BacktestResultRecord.symbols == params.symbols,
                    BacktestResultRecord.timeframe == params.timeframe,
                    BacktestResultRecord.date_from == params.date_from,
                    BacktestResultRecord.date_to == params.date_to,
                    BacktestResultRecord.quantity == params.quantity,
                    BacktestResultRecord.stoploss_pct == params.stoploss_pct,
                    BacktestResultRecord.target_pct == params.target_pct,
                    BacktestResultRecord.trailing_pct == params.trailing_pct,
                    BacktestResultRecord.max_cycles_per_day == params.max_cycles_per_day,
                    BacktestResultRecord.start_time == params.start_time,
                    BacktestResultRecord.end_time == params.end_time,
                    BacktestResultRecord.charges_enabled == params.charges_enabled,
                    BacktestResultRecord.strategy_params_json == params.strategy_params_json,
                )
            ).scalar_one_or_none()

            now = datetime.now()
            # `result` is whatever backtest_server.py/run_backtest.py just
            # computed (equity_curve points carry a `date` bucket, etc.) —
            # default=str covers any date/datetime that slips through
            # without every caller having to pre-serialize its own dict.
            result_json = json.dumps(result, default=str)

            if existing is not None:
                existing.result_json = result_json
                existing.updated_at = now
                record = existing
            else:
                record = BacktestResultRecord(
                    strategy_name=params.strategy_name,
                    symbols=params.symbols,
                    timeframe=params.timeframe,
                    date_from=params.date_from,
                    date_to=params.date_to,
                    quantity=params.quantity,
                    stoploss_pct=params.stoploss_pct,
                    target_pct=params.target_pct,
                    trailing_pct=params.trailing_pct,
                    max_cycles_per_day=params.max_cycles_per_day,
                    start_time=params.start_time,
                    end_time=params.end_time,
                    charges_enabled=params.charges_enabled,
                    strategy_params_json=params.strategy_params_json,
                    result_json=result_json,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)

            session.flush()
            return _record_to_result(record)

    def list_results(self, strategy_name: str) -> List[BacktestResult]:
        with unit_of_work(self._session_factory) as session:
            records = session.execute(
                select(BacktestResultRecord)
                .where(BacktestResultRecord.strategy_name == strategy_name)
                .order_by(BacktestResultRecord.updated_at.desc())
            ).scalars().all()
            return [_record_to_result(r) for r in records]

    def get_result(self, result_id: int) -> Optional[BacktestResult]:
        with unit_of_work(self._session_factory) as session:
            record = session.get(BacktestResultRecord, result_id)
            return _record_to_result(record) if record else None

    def delete_result(self, result_id: int) -> None:
        with unit_of_work(self._session_factory) as session:
            record = session.get(BacktestResultRecord, result_id)
            if record is not None:
                session.delete(record)
