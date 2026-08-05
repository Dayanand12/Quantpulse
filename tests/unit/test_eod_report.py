import datetime as dt

import pandas as pd

from core.domain.enums import OrderSide
from core.domain.models import Deployment, StrategyConfig
from infrastructure.persistence.database import Base, create_session_factory, unit_of_work
from infrastructure.persistence.models import TradeRecord
from infrastructure.persistence.sql_deployment_repository import SqlDeploymentRepository
from services.eod_report import generate_all_time_report, generate_eod_report


def _make_env(tmp_path):
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(session_factory().get_bind())
    deployment_repository = SqlDeploymentRepository(session_factory)

    deployment_repository.save_deployment(
        Deployment(
            id="dep1",
            strategy_name="orb_reversal",
            symbols=("RELIANCE",),
            capital=100_000.0,
            config=StrategyConfig(),
        )
    )
    return session_factory, deployment_repository


def _insert_trade(session_factory, closed_at, pnl, deployment_id="dep1"):
    with unit_of_work(session_factory) as session:
        session.add(
            TradeRecord(
                symbol="RELIANCE",
                side=OrderSide.SELL.value,
                quantity=50,
                entry_price=250.0,
                exit_price=245.0,
                pnl=pnl,
                closed_at=closed_at,
                deployment_id=deployment_id,
                strategy_name="orb_reversal",
            )
        )


def test_eod_report_only_includes_trades_from_the_requested_day(tmp_path):
    session_factory, deployment_repository = _make_env(tmp_path)
    _insert_trade(session_factory, dt.datetime(2026, 1, 1, 10, 0), pnl=100.0)
    _insert_trade(session_factory, dt.datetime(2026, 1, 2, 10, 0), pnl=200.0)  # different day

    path = generate_eod_report(
        session_factory, deployment_repository, dt.date(2026, 1, 1), str(tmp_path)
    )

    trades_df = pd.read_excel(path, sheet_name="Trades")
    assert len(trades_df) == 1
    assert trades_df.iloc[0]["PnL"] == 100.0


def test_all_time_report_includes_every_trade_regardless_of_day(tmp_path):
    session_factory, deployment_repository = _make_env(tmp_path)
    _insert_trade(session_factory, dt.datetime(2026, 1, 1, 10, 0), pnl=100.0)
    _insert_trade(session_factory, dt.datetime(2026, 3, 15, 10, 0), pnl=200.0)
    _insert_trade(session_factory, dt.datetime(2026, 6, 30, 10, 0), pnl=-50.0)

    path = generate_all_time_report(session_factory, deployment_repository, str(tmp_path))

    trades_df = pd.read_excel(path, sheet_name="Trades")
    assert len(trades_df) == 3
    assert trades_df["PnL"].sum() == 250.0

    metrics_df = pd.read_excel(path, sheet_name="Strategy Metrics")
    overall = metrics_df[metrics_df["Strategy"] == "ALL STRATEGIES (combined)"].iloc[0]
    assert overall["Total Trades"] == 3
    assert overall["Total P&L"] == 250.0


def test_all_time_report_overwrites_the_same_file_on_regeneration(tmp_path):
    session_factory, deployment_repository = _make_env(tmp_path)
    _insert_trade(session_factory, dt.datetime(2026, 1, 1, 10, 0), pnl=100.0)

    first = generate_all_time_report(session_factory, deployment_repository, str(tmp_path))
    _insert_trade(session_factory, dt.datetime(2026, 1, 2, 10, 0), pnl=50.0)
    second = generate_all_time_report(session_factory, deployment_repository, str(tmp_path))

    assert first == second
    trades_df = pd.read_excel(second, sheet_name="Trades")
    assert len(trades_df) == 2
