import datetime as dt

from core.domain.enums import OrderSide
from core.domain.models import Trade
from runners.backtesting.result_persistence import breakdown_rows, symbols_identity


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
