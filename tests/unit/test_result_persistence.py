import datetime as dt

from core.domain.enums import OrderSide
from core.domain.models import StrategyConfig, Trade
from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_backtest_result_repository import SqlBacktestResultRepository
from runners.backtesting.result_persistence import (
    breakdown_rows,
    save_per_symbol_results,
    symbols_identity,
)


def make_trade(**overrides):
    defaults = dict(
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=50,
        entry_price=100.0,
        exit_price=102.0,
        pnl=100.0,
        closed_at=dt.datetime(2025, 1, 1, 10, 0),
        market_condition="Trending / High Volume / Above VWAP",
    )
    defaults.update(overrides)
    return Trade(**defaults)


def test_breakdown_rows_groups_by_key_fn():
    trades = [
        make_trade(symbol="RELIANCE"),
        make_trade(symbol="RELIANCE"),
        make_trade(symbol="TCS"),
    ]

    rows = breakdown_rows(trades, lambda t: t.symbol)

    names = {r["strategy_name"] for r in rows}
    assert names == {"RELIANCE", "TCS"}


def test_breakdown_rows_shape_matches_what_the_analysis_tab_expects():
    # This is the exact shape StrategyTable.tsx renders — the regression
    # this guards is real: run_backtest.py's CLI path used to save a
    # result missing by_symbol/by_market_condition/by_side entirely,
    # which crashed the Analysis tab (blank screen) for every CLI-saved
    # result, since backtest_server.py's API path always included them.
    rows = breakdown_rows([make_trade()], lambda t: t.symbol)

    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {"strategy_name", "deployment_id", "capital", "metrics"}
    assert row["metrics"]["total_trades"] == 1


def test_breakdown_rows_skips_trades_where_key_fn_returns_none():
    trades = [make_trade(market_condition=None), make_trade(market_condition="Trending")]

    rows = breakdown_rows(trades, lambda t: t.market_condition)

    assert len(rows) == 1
    assert rows[0]["strategy_name"] == "Trending"


def test_breakdown_rows_sorted_by_trade_count_descending():
    trades = [make_trade(symbol="A")] + [make_trade(symbol="B") for _ in range(3)]

    rows = breakdown_rows(trades, lambda t: t.symbol)

    assert [r["strategy_name"] for r in rows] == ["B", "A"]


def test_breakdown_rows_empty_trades_returns_empty_list():
    assert breakdown_rows([], lambda t: t.symbol) == []


def test_symbols_identity_full_watchlist_sentinel():
    assert symbols_identity(None, is_full_watchlist=True) == "WATCHLIST"
    assert symbols_identity([], is_full_watchlist=False) == "WATCHLIST"


def test_symbols_identity_sorts_and_uppercases():
    assert symbols_identity(["tcs", "RELIANCE"], is_full_watchlist=False) == "RELIANCE,TCS"


def make_result_repo(tmp_path):
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(session_factory().get_bind())
    return SqlBacktestResultRepository(session_factory)


def test_save_per_symbol_results_creates_one_row_per_symbol(tmp_path):
    repo = make_result_repo(tmp_path)
    trades = [
        make_trade(symbol="RELIANCE"),
        make_trade(symbol="RELIANCE"),
        make_trade(symbol="TCS"),
    ]

    saved = save_per_symbol_results(
        repo, strategy_name="my_strategy", symbols_used=["RELIANCE", "TCS"], all_trades=trades,
        config=StrategyConfig(), charges_enabled=True,
        date_from=dt.date(2025, 1, 1), date_to=dt.date(2025, 12, 31), capital=100_000,
    )

    assert set(saved.keys()) == {"RELIANCE", "TCS"}
    assert saved["RELIANCE"].result["metrics"]["total_trades"] == 2
    assert saved["TCS"].result["metrics"]["total_trades"] == 1
    # Each row's own identity is that ONE symbol, not a joined list.
    assert saved["RELIANCE"].params.symbols == "RELIANCE"
    assert saved["TCS"].params.symbols == "TCS"

    all_results = repo.list_results("my_strategy")
    assert len(all_results) == 2


def test_save_per_symbol_results_includes_symbols_with_zero_trades(tmp_path):
    # A symbol that never triggered an entry is itself an answer ("this
    # strategy doesn't fire on this stock with these params"), not
    # something to silently drop from storage.
    repo = make_result_repo(tmp_path)

    saved = save_per_symbol_results(
        repo, strategy_name="my_strategy", symbols_used=["RELIANCE", "TCS"], all_trades=[],
        config=StrategyConfig(), charges_enabled=True,
        date_from=dt.date(2025, 1, 1), date_to=dt.date(2025, 12, 31), capital=100_000,
    )

    assert saved["RELIANCE"].result["metrics"]["total_trades"] == 0
    assert saved["TCS"].result["metrics"]["total_trades"] == 0


def test_save_per_symbol_results_equity_curve_is_scoped_to_its_own_symbol(tmp_path):
    repo = make_result_repo(tmp_path)
    trades = [
        make_trade(symbol="RELIANCE", pnl=100.0, closed_at=dt.datetime(2025, 1, 1, 10, 0)),
        make_trade(symbol="RELIANCE", pnl=50.0, closed_at=dt.datetime(2025, 1, 2, 10, 0)),
        make_trade(symbol="TCS", pnl=-30.0, closed_at=dt.datetime(2025, 1, 1, 10, 0)),
    ]

    saved = save_per_symbol_results(
        repo, strategy_name="my_strategy", symbols_used=["RELIANCE", "TCS"], all_trades=trades,
        config=StrategyConfig(), charges_enabled=True,
        date_from=dt.date(2025, 1, 1), date_to=dt.date(2025, 12, 31), capital=100_000,
    )

    reliance_curve = saved["RELIANCE"].result["equity_curve"]
    tcs_curve = saved["TCS"].result["equity_curve"]
    assert len(reliance_curve) == 2  # only RELIANCE's own 2 trades
    assert len(tcs_curve) == 1  # only TCS's own 1 trade


def test_save_per_symbol_results_upserts_on_rerun_not_duplicates(tmp_path):
    repo = make_result_repo(tmp_path)
    trades = [make_trade(symbol="RELIANCE")]
    kwargs = dict(
        strategy_name="my_strategy", symbols_used=["RELIANCE"], all_trades=trades,
        config=StrategyConfig(), charges_enabled=True,
        date_from=dt.date(2025, 1, 1), date_to=dt.date(2025, 12, 31), capital=100_000,
    )

    first = save_per_symbol_results(repo, **kwargs)
    second = save_per_symbol_results(repo, **kwargs)

    assert first["RELIANCE"].id == second["RELIANCE"].id
    assert len(repo.list_results("my_strategy")) == 1
