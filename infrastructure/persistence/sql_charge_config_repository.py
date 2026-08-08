"""IChargeConfigRepository implemented over SQLAlchemy — single row, id=1."""

import dataclasses

from sqlalchemy.orm import sessionmaker

from core.application.interfaces.charge_config_repository import IChargeConfigRepository
from core.domain.charges import ChargeConfig
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import ChargeConfigRecord

_SINGLETON_ID = 1


def _record_to_config(record: ChargeConfigRecord) -> ChargeConfig:
    return ChargeConfig(
        brokerage_pct=record.brokerage_pct,
        brokerage_max_per_order=record.brokerage_max_per_order,
        stt_pct=record.stt_pct,
        exchange_txn_pct=record.exchange_txn_pct,
        sebi_pct=record.sebi_pct,
        stamp_duty_pct=record.stamp_duty_pct,
        gst_pct=record.gst_pct,
    )


class SqlChargeConfigRepository(IChargeConfigRepository):
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def get_config(self) -> ChargeConfig:
        with unit_of_work(self._session_factory) as session:
            record = session.get(ChargeConfigRecord, _SINGLETON_ID)
            return _record_to_config(record) if record else ChargeConfig()

    def save_config(self, config: ChargeConfig) -> ChargeConfig:
        with unit_of_work(self._session_factory) as session:
            record = session.get(ChargeConfigRecord, _SINGLETON_ID)
            if record is None:
                record = ChargeConfigRecord(id=_SINGLETON_ID)
                session.add(record)

            for field in dataclasses.fields(config):
                setattr(record, field.name, getattr(config, field.name))

        return config
