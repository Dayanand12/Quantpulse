import datetime as dt

import pandas as pd

from core.domain.enums import OrderSide
from core.domain.models import Trade
from runners.backtesting.report import write_backtest_report


def _trade(symbol, side, pnl, market_condition, closed_at=None):
    return Trade(
        symbol=symbol,
        side=side,
        quantity=50,
        entry_price=250.0,
        exit_price=245.0 if side == OrderSide.SELL else 255.0,
        pnl=pnl,
        closed_at=closed_at or dt.datetime(2026, 1, 5, 10, 0),
        market_condition=market_condition,
    )


def test_writes_every_expected_sheet(tmp_path):
    trades = [
        _trade("RELIANCE", OrderSide.SELL, 100.0, "Trending / High Volume / Above VWAP"),
        _trade("TCS", OrderSide.BUY, -50.0, "Ranging / Normal Volume / Below VWAP"),
    ]
    path = str(tmp_path / "report.xlsx")

    write_backtest_report(trades, "RELIANCE+TCS", "orb_reversal", 100_000, path)

    xls = pd.ExcelFile(path)
    assert set(xls.sheet_names) == {"Trades", "Summary", "By Symbol", "By Market Condition", "By Side"}


def test_by_symbol_breaks_down_correctly(tmp_path):
    trades = [
        _trade("RELIANCE", OrderSide.SELL, 100.0, "Trending / High Volume / Above VWAP"),
        _trade("RELIANCE", OrderSide.SELL, 50.0, "Trending / High Volume / Above VWAP"),
        _trade("TCS", OrderSide.SELL, -30.0, "Ranging / Normal Volume / Below VWAP"),
    ]
    path = str(tmp_path / "report.xlsx")

    write_backtest_report(trades, "RELIANCE+TCS", "orb_reversal", 100_000, path)

    by_symbol = pd.read_excel(path, sheet_name="By Symbol").set_index("Strategy")
    assert by_symbol.loc["RELIANCE", "Total Trades"] == 2
    assert by_symbol.loc["RELIANCE", "Total P&L"] == 150.0
    assert by_symbol.loc["TCS", "Total Trades"] == 1
    assert by_symbol.loc["TCS", "Total P&L"] == -30.0


def test_by_market_condition_breaks_down_correctly(tmp_path):
    trades = [
        _trade("RELIANCE", OrderSide.SELL, 100.0, "Trending / High Volume / Above VWAP"),
        _trade("TCS", OrderSide.SELL, 40.0, "Trending / High Volume / Above VWAP"),
        _trade("INFY", OrderSide.SELL, -30.0, "Ranging / Normal Volume / Below VWAP"),
    ]
    path = str(tmp_path / "report.xlsx")

    write_backtest_report(trades, "WATCHLIST", "orb_reversal", 100_000, path)

    by_condition = pd.read_excel(path, sheet_name="By Market Condition").set_index("Strategy")
    assert by_condition.loc["Trending / High Volume / Above VWAP", "Total Trades"] == 2
    assert by_condition.loc["Trending / High Volume / Above VWAP", "Total P&L"] == 140.0
    assert by_condition.loc["Ranging / Normal Volume / Below VWAP", "Total Trades"] == 1


def test_trades_without_a_market_condition_are_excluded_from_that_breakdown(tmp_path):
    trades = [
        _trade("RELIANCE", OrderSide.SELL, 100.0, None),
        _trade("TCS", OrderSide.SELL, 40.0, "Trending / High Volume / Above VWAP"),
    ]
    path = str(tmp_path / "report.xlsx")

    write_backtest_report(trades, "RELIANCE+TCS", "orb_reversal", 100_000, path)

    by_condition = pd.read_excel(path, sheet_name="By Market Condition")
    assert by_condition["Total Trades"].sum() == 1  # only the labeled trade


def test_by_side_breaks_down_buy_vs_sell(tmp_path):
    trades = [
        _trade("RELIANCE", OrderSide.SELL, 100.0, "Trending / High Volume / Above VWAP"),
        _trade("TCS", OrderSide.BUY, 50.0, "Trending / High Volume / Above VWAP"),
    ]
    path = str(tmp_path / "report.xlsx")

    write_backtest_report(trades, "RELIANCE+TCS", "vwap_reclaim", 100_000, path)

    by_side = pd.read_excel(path, sheet_name="By Side").set_index("Strategy")
    assert by_side.loc["SELL", "Total Trades"] == 1
    assert by_side.loc["BUY", "Total Trades"] == 1


def test_handles_zero_trades_without_crashing(tmp_path):
    path = str(tmp_path / "report.xlsx")

    write_backtest_report([], "RELIANCE", "orb_reversal", 100_000, path)

    xls = pd.ExcelFile(path)
    assert "By Symbol" in xls.sheet_names
    assert len(pd.read_excel(path, sheet_name="By Symbol")) == 0
