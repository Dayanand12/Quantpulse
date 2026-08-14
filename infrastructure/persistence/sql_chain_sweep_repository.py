"""IChainSweepRepository implemented over SQLAlchemy. Every write goes
through its own session — chain_sweep_runner.py calls save() from a
background thread that is NOT the request thread that created the sweep,
same reasoning as sql_batch_job_repository.py.
"""

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.application.interfaces.chain_sweep_repository import IChainSweepRepository
from core.domain.chain_sweep import ChainSweep, ChainSweepContract
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import ChainSweepRecord


def _contract_to_dict(c: ChainSweepContract) -> dict:
    return {
        "symbol": c.symbol,
        "status": c.status,
        "saved_result_id": c.saved_result_id,
        "error": c.error,
        "total_trades": c.total_trades,
        "total_pnl": c.total_pnl,
        "win_rate": c.win_rate,
        "profit_factor": c.profit_factor,
    }


def _contract_from_dict(d: dict) -> ChainSweepContract:
    return ChainSweepContract(
        symbol=d["symbol"],
        status=d.get("status", "pending"),
        saved_result_id=d.get("saved_result_id"),
        error=d.get("error"),
        total_trades=d.get("total_trades"),
        total_pnl=d.get("total_pnl"),
        win_rate=d.get("win_rate"),
        profit_factor=d.get("profit_factor"),
    )


def _record_to_sweep(record: ChainSweepRecord) -> ChainSweep:
    return ChainSweep(
        id=record.id,
        strategy_name=record.strategy_name,
        underlying=record.underlying,
        category=record.category,
        expiry_filter=record.expiry_filter,
        shared_config=json.loads(record.shared_config_json),
        contracts=[_contract_from_dict(d) for d in json.loads(record.contracts_json)],
        status=record.status,
        error=record.error,
        created_at=record.created_at,
        finished_at=record.finished_at,
    )


class SqlChainSweepRepository(IChainSweepRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def create(self, sweep: ChainSweep) -> ChainSweep:
        with unit_of_work(self._session_factory) as session:
            record = ChainSweepRecord(
                strategy_name=sweep.strategy_name,
                underlying=sweep.underlying,
                category=sweep.category,
                expiry_filter=sweep.expiry_filter,
                status=sweep.status,
                shared_config_json=json.dumps(sweep.shared_config, default=str),
                contracts_json=json.dumps([_contract_to_dict(c) for c in sweep.contracts]),
                error=sweep.error,
                created_at=sweep.created_at or datetime.now(),
                finished_at=sweep.finished_at,
            )
            session.add(record)
            session.flush()
            return _record_to_sweep(record)

    def save(self, sweep: ChainSweep) -> ChainSweep:
        with unit_of_work(self._session_factory) as session:
            record = session.get(ChainSweepRecord, sweep.id)
            if record is None:
                raise ValueError(f"No stored chain sweep with id {sweep.id}")
            record.status = sweep.status
            record.contracts_json = json.dumps([_contract_to_dict(c) for c in sweep.contracts])
            record.error = sweep.error
            record.finished_at = sweep.finished_at
            session.flush()
            return _record_to_sweep(record)

    def get(self, sweep_id: int) -> Optional[ChainSweep]:
        with unit_of_work(self._session_factory) as session:
            record = session.get(ChainSweepRecord, sweep_id)
            return _record_to_sweep(record) if record else None

    def list_for_strategy(self, strategy_name: str, limit: int = 20) -> List[ChainSweep]:
        with unit_of_work(self._session_factory) as session:
            records = session.execute(
                select(ChainSweepRecord)
                .where(ChainSweepRecord.strategy_name == strategy_name)
                .order_by(ChainSweepRecord.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return [_record_to_sweep(r) for r in records]
