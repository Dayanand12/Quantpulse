import dataclasses

from core.domain.charges import ChargeConfig
from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_charge_config_repository import SqlChargeConfigRepository


def make_repo(tmp_path):
    db_path = tmp_path / "test.db"
    session_factory = create_session_factory(f"sqlite:///{db_path}")
    Base.metadata.create_all(session_factory().get_bind())
    return SqlChargeConfigRepository(session_factory)


def test_get_config_returns_defaults_when_nothing_saved(tmp_path):
    repo = make_repo(tmp_path)

    assert repo.get_config() == ChargeConfig()


def test_save_then_get_round_trips(tmp_path):
    repo = make_repo(tmp_path)
    custom = dataclasses.replace(ChargeConfig(), brokerage_pct=0.0005, gst_pct=0.2)

    repo.save_config(custom)

    assert repo.get_config() == custom


def test_saving_twice_overwrites_the_same_row_not_a_second_one(tmp_path):
    repo = make_repo(tmp_path)

    repo.save_config(dataclasses.replace(ChargeConfig(), brokerage_pct=0.0004))
    repo.save_config(dataclasses.replace(ChargeConfig(), brokerage_pct=0.0007))

    assert repo.get_config().brokerage_pct == 0.0007
