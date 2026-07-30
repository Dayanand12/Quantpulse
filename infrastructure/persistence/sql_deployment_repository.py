"""IDeploymentRepository implemented over SQLAlchemy."""

import json
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.application.interfaces.deployment_repository import IDeploymentRepository
from core.domain.models import Deployment, StrategyConfig
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import DeploymentRecord


def _to_domain(record: DeploymentRecord) -> Deployment:
    return Deployment(
        id=record.id,
        strategy_name=record.strategy_name,
        symbols=tuple(json.loads(record.symbols_json)),
        capital=record.capital,
        config=StrategyConfig(
            quantity=record.quantity,
            stoploss_pct=record.stoploss_pct,
            target_pct=record.target_pct,
            trailing_pct=record.trailing_pct,
            max_cycles_per_day=record.max_cycles_per_day,
            start_time=record.start_time,
            end_time=record.end_time,
            timeframe=record.timeframe,
        ),
        enabled=record.enabled,
    )


class SqlDeploymentRepository(IDeploymentRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def list_deployments(self) -> List[Deployment]:
        with unit_of_work(self._session_factory) as session:
            records = session.scalars(select(DeploymentRecord))
            return [_to_domain(r) for r in records]

    def get_deployment(self, deployment_id: str) -> Optional[Deployment]:
        with unit_of_work(self._session_factory) as session:
            record = session.get(DeploymentRecord, deployment_id)
            return _to_domain(record) if record else None

    def save_deployment(self, deployment: Deployment) -> None:
        with unit_of_work(self._session_factory) as session:
            record = session.get(DeploymentRecord, deployment.id) or DeploymentRecord(
                id=deployment.id
            )
            record.strategy_name = deployment.strategy_name
            record.symbols_json = json.dumps(list(deployment.symbols))
            record.capital = deployment.capital
            record.quantity = deployment.config.quantity
            record.stoploss_pct = deployment.config.stoploss_pct
            record.target_pct = deployment.config.target_pct
            record.trailing_pct = deployment.config.trailing_pct
            record.max_cycles_per_day = deployment.config.max_cycles_per_day
            record.enabled = deployment.enabled
            record.start_time = deployment.config.start_time
            record.end_time = deployment.config.end_time
            record.timeframe = deployment.config.timeframe
            session.merge(record)

    def delete_deployment(self, deployment_id: str) -> None:
        with unit_of_work(self._session_factory) as session:
            record = session.get(DeploymentRecord, deployment_id)
            if record:
                session.delete(record)
