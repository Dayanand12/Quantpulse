import datetime as dt

from core.application.interfaces.trade_repository import TradeFilter
from core.domain.enums import OrderSide
from infrastructure.persistence.database import Base, create_session_factory, unit_of_work
from infrastructure.persistence.models import TradeRecord
from infrastructure.persistence.sql_trade_repository import SqlTradeRepository


def make_repo(tmp_path):
    db_path = tmp_path / "test.db"
    session_factory = create_session_factory(f"sqlite:///{db_path}")
    Base.metadata.create_all(session_factory().get_bind())
    return session_factory, SqlTradeRepository(session_factory)


def add_trade(session_factory, **overrides):
    defaults = dict(
        symbol="RELIANCE",
        side=OrderSide.SELL.value,
        quantity=10,
        entry_price=100.0,
        exit_price=95.0,
        pnl=50.0,
        closed_at=dt.datetime(2026, 1, 1, 10, 0),
        initial_stop_loss=102.0,
        deployment_id="dep1",
        strategy_name="orb_reversal",
    )
    defaults.update(overrides)
    with unit_of_work(session_factory) as session:
        session.add(TradeRecord(**defaults))


def test_list_is_empty_when_nothing_persisted(tmp_path):
    _, repo = make_repo(tmp_path)

    assert repo.list_trades() == []


def test_list_returns_all_trades_ordered_by_closed_at(tmp_path):
    session_factory, repo = make_repo(tmp_path)
    add_trade(session_factory, closed_at=dt.datetime(2026, 1, 2), pnl=10)
    add_trade(session_factory, closed_at=dt.datetime(2026, 1, 1), pnl=20)

    trades = repo.list_trades()

    assert [t.closed_at for t in trades] == [dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 2)]


def test_filters_by_strategy_name(tmp_path):
    session_factory, repo = make_repo(tmp_path)
    add_trade(session_factory, strategy_name="orb_reversal")
    add_trade(session_factory, strategy_name="ema_crossover")

    trades = repo.list_trades(TradeFilter(strategy_name="ema_crossover"))

    assert len(trades) == 1
    assert trades[0].strategy_name == "ema_crossover"


def test_filters_by_symbol(tmp_path):
    session_factory, repo = make_repo(tmp_path)
    add_trade(session_factory, symbol="RELIANCE")
    add_trade(session_factory, symbol="TCS")

    trades = repo.list_trades(TradeFilter(symbol="TCS"))

    assert len(trades) == 1
    assert trades[0].symbol == "TCS"


def test_filters_by_date_range_inclusive(tmp_path):
    session_factory, repo = make_repo(tmp_path)
    add_trade(session_factory, closed_at=dt.datetime(2025, 12, 31, 15, 0))
    add_trade(session_factory, closed_at=dt.datetime(2026, 1, 1, 9, 20))
    add_trade(session_factory, closed_at=dt.datetime(2026, 1, 5, 12, 0))
    add_trade(session_factory, closed_at=dt.datetime(2026, 1, 6, 9, 20))

    trades = repo.list_trades(
        TradeFilter(date_from=dt.date(2026, 1, 1), date_to=dt.date(2026, 1, 5))
    )

    assert len(trades) == 2
    assert all(dt.date(2026, 1, 1) <= t.closed_at.date() <= dt.date(2026, 1, 5) for t in trades)


def test_date_range_excludes_trades_outside_market_hours_on_boundary_days(tmp_path):
    # date_from/date_to mean "that trading day" (09:15-15:30), not the
    # calendar day — a stray midnight timestamp on the boundary date must
    # not leak into a single-day filter.
    session_factory, repo = make_repo(tmp_path)
    add_trade(session_factory, closed_at=dt.datetime(2026, 1, 5, 0, 0))  # before market open
    add_trade(session_factory, closed_at=dt.datetime(2026, 1, 5, 9, 15))  # exactly market open
    add_trade(session_factory, closed_at=dt.datetime(2026, 1, 5, 15, 30))  # exactly market close
    add_trade(session_factory, closed_at=dt.datetime(2026, 1, 5, 23, 59))  # after market close

    trades = repo.list_trades(
        TradeFilter(date_from=dt.date(2026, 1, 5), date_to=dt.date(2026, 1, 5))
    )

    assert len(trades) == 2
    assert {t.closed_at.time() for t in trades} == {dt.time(9, 15), dt.time(15, 30)}


def test_maps_all_fields_correctly(tmp_path):
    session_factory, repo = make_repo(tmp_path)
    add_trade(
        session_factory,
        symbol="INFY",
        side=OrderSide.BUY.value,
        quantity=5,
        entry_price=1500.0,
        exit_price=1520.0,
        pnl=100.0,
        initial_stop_loss=1480.0,
        deployment_id="depX",
        strategy_name="ema_crossover",
    )

    [trade] = repo.list_trades()

    assert trade.symbol == "INFY"
    assert trade.side == OrderSide.BUY
    assert trade.quantity == 5
    assert trade.entry_price == 1500.0
    assert trade.exit_price == 1520.0
    assert trade.pnl == 100.0
    assert trade.initial_stop_loss == 1480.0
    assert trade.deployment_id == "depX"
    assert trade.strategy_name == "ema_crossover"
