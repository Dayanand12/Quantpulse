"""IBatchJobRepository implemented over SQLAlchemy. Every write goes
through its own session (see unit_of_work) — the background runner
(runners/backtesting/batch_job_runner.py) calls save() from a thread that
is NOT the request thread that created the job, so it needs a fresh
session/connection of its own rather than reusing anything request-scoped.
"""

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.application.interfaces.batch_job_repository import IBatchJobRepository
from core.domain.batch_job import BatchJob, BatchJobScenario
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import BatchJobRecord


def _scenario_to_dict(s: BatchJobScenario) -> dict:
    return {
        "label": s.label,
        "overrides": s.overrides,
        "config_overrides": s.config_overrides,
        "status": s.status,
        "saved_result_id": s.saved_result_id,
        "error": s.error,
    }


def _scenario_from_dict(d: dict) -> BatchJobScenario:
    return BatchJobScenario(
        label=d["label"],
        overrides=d["overrides"],
        config_overrides=d.get("config_overrides", {}),
        status=d.get("status", "pending"),
        saved_result_id=d.get("saved_result_id"),
        error=d.get("error"),
    )


def _record_to_job(record: BatchJobRecord) -> BatchJob:
    return BatchJob(
        id=record.id,
        strategy_name=record.strategy_name,
        status=record.status,
        shared_config=json.loads(record.shared_config_json),
        scenarios=[_scenario_from_dict(d) for d in json.loads(record.scenarios_json)],
        error=record.error,
        created_at=record.created_at,
        finished_at=record.finished_at,
    )


class SqlBatchJobRepository(IBatchJobRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def create(self, job: BatchJob) -> BatchJob:
        with unit_of_work(self._session_factory) as session:
            record = BatchJobRecord(
                strategy_name=job.strategy_name,
                status=job.status,
                shared_config_json=json.dumps(job.shared_config, default=str),
                scenarios_json=json.dumps([_scenario_to_dict(s) for s in job.scenarios]),
                error=job.error,
                created_at=job.created_at or datetime.now(),
                finished_at=job.finished_at,
            )
            session.add(record)
            session.flush()
            return _record_to_job(record)

    def save(self, job: BatchJob) -> BatchJob:
        with unit_of_work(self._session_factory) as session:
            record = session.get(BatchJobRecord, job.id)
            if record is None:
                raise ValueError(f"No stored batch job with id {job.id}")
            record.status = job.status
            record.scenarios_json = json.dumps([_scenario_to_dict(s) for s in job.scenarios])
            record.error = job.error
            record.finished_at = job.finished_at
            session.flush()
            return _record_to_job(record)

    def get(self, job_id: int) -> Optional[BatchJob]:
        with unit_of_work(self._session_factory) as session:
            record = session.get(BatchJobRecord, job_id)
            return _record_to_job(record) if record else None

    def list_for_strategy(self, strategy_name: str, limit: int = 20) -> List[BatchJob]:
        with unit_of_work(self._session_factory) as session:
            records = session.execute(
                select(BatchJobRecord)
                .where(BatchJobRecord.strategy_name == strategy_name)
                .order_by(BatchJobRecord.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return [_record_to_job(r) for r in records]
