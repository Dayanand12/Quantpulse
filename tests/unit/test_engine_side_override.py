import datetime as dt
from typing import Dict, List

import polars as pl

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide
from core.domain.models import StrategyConfig
from runners.backtesting.engine import run_backtest

# snapshot_builder._MIN_BARS — the first 24 bars are warm-up (dropped from
# the snapshot series), so the 25th bar (index 24) is the first one a
# strategy ever sees. Mirrors tests/unit/test_backtest_engine.py's own
# constant/helpers; duplicated here (rather than imported) so this file
# doesn't depend on that module's strategies/test_always_* fixtures.
_FIRST_TRADEABLE_INDEX = 24


def _bar(day: dt.date, index: int, open_, high, low, close, volume=1000.0):
    return {
        "date": dt.datetime.combine(day, dt.time(9, 15)) + dt.timedelta(minutes=index),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


def _flat_warmup(day: dt.date, count: int, price: float):
    return [_bar(day, i, price, price, price, price) for i in range(count)]


class _AlwaysEnterBuyStrategy(IStrategy):
    """A strategy fixed as BUY — used to verify side_override can still
    make it trade SELL for a given run, e.g. to sell/write an option."""

    name = "always_enter_buy_test_fixture"
    display_name = "Always Enter (BUY, test fixture)"
    side = OrderSide.BUY

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        return list(symbols)


def _one_trade_df():
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX, 100.0)
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX, 100.0, 100.0, 100.0, 100.0))
    # Next bar swings both directions so either a BUY or a SELL entry hits
    # its stop loss on this same bar — same price path for both directions.
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX + 1, 100.0, 101.0, 99.0, 100.2))
    return pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))


def test_side_override_none_uses_the_strategys_own_side():
    df = _one_trade_df()
    config = StrategyConfig(stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1)

    trades = run_backtest(_AlwaysEnterBuyStrategy(), "TEST", df, config)

    assert len(trades) == 1
    assert trades[0].side == OrderSide.BUY


def test_side_override_sell_trades_sell_despite_strategys_own_buy_side():
    # This is exactly what selling/writing a CE or PE needs: a strategy
    # whose own `side` is BUY, run as SELL for one call.
    df = _one_trade_df()
    config = StrategyConfig(stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1)

    trades = run_backtest(
        _AlwaysEnterBuyStrategy(), "TEST", df, config, side_override=OrderSide.SELL,
    )

    assert len(trades) == 1
    assert trades[0].side == OrderSide.SELL


def test_side_override_flips_pnl_sign_on_the_identical_price_path():
    # A falling price should hurt a BUY position and help the SAME
    # strategy run as SELL — exactly the mechanic that makes selling/
    # writing an option's premium (rather than buying it) profit when the
    # premium falls.
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX, 100.0)
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX, 100.0, 100.0, 100.0, 100.0))
    # BUY: low 98.5 breaches its 99.2 stop-loss -> SL exit, a loss.
    # SELL: high 100.2 doesn't breach its 100.8 stop-loss, low 98.5 doesn't
    # reach its 98.0 target, but the close (98.7) breaches the 0.1%
    # trailing stop -> TRAIL exit at 98.7, a profit (price fell).
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX + 1, 100.0, 100.2, 98.5, 98.7))
    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig(stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1)

    buy_trades = run_backtest(_AlwaysEnterBuyStrategy(), "TEST", df, config)
    sell_trades = run_backtest(
        _AlwaysEnterBuyStrategy(), "TEST", df, config, side_override=OrderSide.SELL,
    )

    assert buy_trades[0].entry_price == sell_trades[0].entry_price == 100.0
    assert buy_trades[0].pnl < 0  # BUY loses when price falls
    assert sell_trades[0].pnl > 0  # the same run, sold instead, profits
