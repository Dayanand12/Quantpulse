import datetime as dt

import polars as pl

from core.domain.charges import ChargeConfig, compute_charges
from core.domain.enums import OrderSide
from core.domain.models import StrategyConfig
from runners.backtesting.engine import run_backtest
from strategies.test_always_long import TestAlwaysLongStrategy
from strategies.test_always_short import TestAlwaysShortStrategy

# snapshot_builder._MIN_BARS — the first 24 bars are warm-up (dropped from
# the snapshot series, matching live_engine's `if df.height < 25: return`),
# so the 25th bar (index 24) is the first one a strategy ever sees.
_FIRST_TRADEABLE_INDEX = 24


def _bar(day: dt.date, index: int, open_, high, low, close, volume=1000.0):
    return {
        "date": dt.datetime.combine(day, dt.time(9, 15)) + dt.timedelta(minutes=index),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


def _flat_warmup(day: dt.date, count: int, price: float):
    return [_bar(day, i, price, price, price, price) for i in range(count)]


def test_sell_side_stop_loss_exits_at_the_stop_price():
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX, 100.0)
    # Entry bar: flat at 100.0 -> SELL entry, stop_loss = 100 * 1.008 = 100.8
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX, 100.0, 100.0, 100.0, 100.0))
    # Next bar's high (101.0) touches the stop -> SL exit at exactly 100.8
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX + 1, 100.0, 101.0, 99.5, 100.5))

    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig(stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1)

    trades = run_backtest(TestAlwaysShortStrategy(), "TEST", df, config)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.side == OrderSide.SELL
    assert trade.entry_price == 100.0
    assert trade.exit_price == 100.8
    assert trade.initial_stop_loss == 100.8
    assert trade.pnl == (100.0 - 100.8) * config.quantity
    assert trade.strategy_name == "test_always_short"


def test_sell_side_target_exits_at_the_target_price():
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX, 100.0)
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX, 100.0, 100.0, 100.0, 100.0))
    # target = 100 * (1 - 2/100) = 98.0 -> low touches it, but trailing_pct
    # is wide (5%) so TRAIL never fires first.
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX + 1, 100.0, 100.2, 98.0, 99.5))

    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig(stoploss_pct=0.8, target_pct=2.0, trailing_pct=5.0)

    trades = run_backtest(TestAlwaysShortStrategy(), "TEST", df, config)

    assert len(trades) == 1
    assert trades[0].exit_price == 98.0
    assert trades[0].pnl == (100.0 - 98.0) * config.quantity


def test_buy_side_stop_loss_is_mirrored():
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX, 100.0)
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX, 100.0, 100.0, 100.0, 100.0))
    # BUY stop_loss = 100 * (1 - 0.8/100) = 99.2 -> low touches it
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX + 1, 100.0, 100.5, 99.0, 99.5))

    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig(stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1)

    trades = run_backtest(TestAlwaysLongStrategy(), "TEST", df, config)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.side == OrderSide.BUY
    assert trade.exit_price == 99.2
    assert trade.pnl == (99.2 - 100.0) * config.quantity


def test_respects_max_cycles_per_day():
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX, 100.0)
    # Every bar from here immediately stops out on the very next bar
    # (tight stop, big swings) so a fresh entry is possible every 2 bars.
    for i in range(20):
        idx = _FIRST_TRADEABLE_INDEX + i * 2
        rows.append(_bar(day, idx, 100.0, 100.0, 100.0, 100.0))
        rows.append(_bar(day, idx + 1, 100.0, 200.0, 100.0, 100.0))  # blows through any SL

    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig(stoploss_pct=0.8, max_cycles_per_day=3)

    trades = run_backtest(TestAlwaysShortStrategy(), "TEST", df, config)

    assert len(trades) == 3


def test_no_entries_outside_the_configured_time_window():
    day = dt.date(2026, 1, 5)
    # First tradeable bar (index 24) is at 09:15 + 24min = 09:39, inside
    # the default 09:20-11:30 window -- narrow the window so it's excluded.
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX + 2, 100.0)

    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig(start_time="09:00", end_time="09:30")

    trades = run_backtest(TestAlwaysShortStrategy(), "TEST", df, config)

    assert trades == []


def test_charges_are_attached_when_a_charge_config_is_given():
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX, 100.0)
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX, 100.0, 100.0, 100.0, 100.0))
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX + 1, 100.0, 101.0, 99.5, 100.5))

    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig(stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1)

    trades = run_backtest(
        TestAlwaysShortStrategy(), "TEST", df, config, charge_config=ChargeConfig()
    )

    assert len(trades) == 1
    trade = trades[0]
    expected = compute_charges(
        trade.entry_price, trade.exit_price, trade.quantity, trade.side, ChargeConfig()
    )
    assert trade.charges == expected.total
    assert trade.net_pnl == trade.pnl - expected.total


def test_no_charge_config_leaves_charges_none():
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX, 100.0)
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX, 100.0, 100.0, 100.0, 100.0))
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX + 1, 100.0, 101.0, 99.5, 100.5))

    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig(stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1)

    trades = run_backtest(TestAlwaysShortStrategy(), "TEST", df, config)

    assert trades[0].charges is None
    assert trades[0].net_pnl is None
