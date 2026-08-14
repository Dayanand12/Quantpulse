import datetime as dt

import polars as pl

from core.application.interfaces.strategy import IStrategy
from core.domain.charges import ChargeConfig, compute_charges
from core.domain.enums import OrderSide
from core.domain.indicator_registry import IndicatorSpec
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


class _SnapshotSpyStrategy(IStrategy):
    """Never enters — just records the exact snapshot dict screen() was
    given, so a test can assert on what got forwarded into it."""

    name = "snapshot_spy"
    display_name = "Snapshot Spy"
    side = OrderSide.SELL

    def __init__(self):
        self.seen_snapshots = []

    def screen(self, snapshot, symbols):
        for symbol in symbols:
            if symbol in snapshot:
                self.seen_snapshots.append(dict(snapshot[symbol]))
        return []


def test_extra_indicators_are_forwarded_into_the_strategy_snapshot():
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX + 5, 100.0)
    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig()
    spy = _SnapshotSpyStrategy()

    run_backtest(spy, "TEST", df, config, extra_indicators=[IndicatorSpec.of("ema", period=20)])

    assert spy.seen_snapshots  # screen() was actually called at least once
    assert all("ema_20" in snap for snap in spy.seen_snapshots)
    # the fixed set must still be there alongside it — additive, not replacing
    assert all("ema9" in snap and "adx" in snap for snap in spy.seen_snapshots)


def test_no_extra_indicators_means_no_dynamic_keys_in_snapshot():
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX + 5, 100.0)
    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig()
    spy = _SnapshotSpyStrategy()

    run_backtest(spy, "TEST", df, config)

    assert spy.seen_snapshots
    assert all("ema_20" not in snap for snap in spy.seen_snapshots)


def test_no_charge_config_leaves_charges_none():
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX, 100.0)
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX, 100.0, 100.0, 100.0, 100.0))
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX + 1, 100.0, 101.0, 99.5, 100.5))

    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig(stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1)

    trades = run_backtest(TestAlwaysShortStrategy(), "TEST", df, config)

    assert trades[0].charges is None


# -----------------------------------------------------------------------
# nifty_ema9/nifty_ema21/nifty_adx — broader-market regime fields joined
# onto every symbol's snapshot (core/domain/strategy_conditions.py's
# VALID_SNAPSHOT_FIELDS). _regime_snapshot_series is monkeypatched
# directly in most of these (not the real NIFTY CSV) so they're isolated
# from both the real data file and engine.py's module-level cache.
# -----------------------------------------------------------------------

import runners.backtesting.engine as engine_module


def test_nifty_regime_fields_join_onto_the_snapshot_by_matching_date(monkeypatch):
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX + 2, 100.0)
    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig()

    nifty_rows = [
        {
            "date": dt.datetime.combine(day, dt.time(9, 15)) + dt.timedelta(minutes=i),
            "nifty_ema9": 100.0 + i, "nifty_ema21": 90.0 + i, "nifty_adx": 40.0,
        }
        for i in range(_FIRST_TRADEABLE_INDEX + 2)
    ]
    nifty_df = pl.DataFrame(nifty_rows).with_columns(pl.col("date").cast(pl.Datetime))
    monkeypatch.setattr(engine_module, "_regime_snapshot_series", lambda timeframe_minutes: nifty_df)

    spy = _SnapshotSpyStrategy()
    run_backtest(spy, "TEST", df, config)

    assert spy.seen_snapshots
    last = spy.seen_snapshots[-1]
    assert last["nifty_ema9"] is not None
    assert last["nifty_ema9"] > last["nifty_ema21"]  # matches the fixture's construction


def test_nifty_regime_fields_are_none_when_nifty_data_unavailable(monkeypatch):
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX + 2, 100.0)
    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig()

    monkeypatch.setattr(engine_module, "_regime_snapshot_series", lambda timeframe_minutes: None)

    spy = _SnapshotSpyStrategy()
    run_backtest(spy, "TEST", df, config)

    assert spy.seen_snapshots
    assert all(snap["nifty_ema9"] is None for snap in spy.seen_snapshots)
    assert all(snap["nifty_ema21"] is None for snap in spy.seen_snapshots)
    assert all(snap["nifty_adx"] is None for snap in spy.seen_snapshots)


def test_regime_lookup_is_skipped_when_backtesting_nifty_itself(monkeypatch):
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX + 2, 100.0)
    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig()

    calls = []
    monkeypatch.setattr(
        engine_module, "_regime_snapshot_series",
        lambda timeframe_minutes: calls.append(timeframe_minutes) or None,
    )

    spy = _SnapshotSpyStrategy()
    run_backtest(spy, "NIFTY 50", df, config)

    assert calls == []  # never looked itself up
    assert all(snap["nifty_ema9"] is None for snap in spy.seen_snapshots)


def test_regime_fields_dont_affect_the_stocks_own_fields_when_nifty_coverage_has_a_gap(monkeypatch):
    # A gap in NIFTY's own coverage (e.g. its history starts later than
    # the stock's) must not crash the join or affect the stock's OWN
    # indicators — just leaves nifty_* None for that bar, same as any
    # other missing snapshot field.
    day = dt.date(2026, 1, 5)
    rows = _flat_warmup(day, _FIRST_TRADEABLE_INDEX + 2, 100.0)
    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))
    config = StrategyConfig()

    nifty_df = pl.DataFrame([{
        "date": dt.datetime.combine(day, dt.time(9, 15)),
        "nifty_ema9": 105.0, "nifty_ema21": 95.0, "nifty_adx": 40.0,
    }]).with_columns(pl.col("date").cast(pl.Datetime))
    monkeypatch.setattr(engine_module, "_regime_snapshot_series", lambda timeframe_minutes: nifty_df)

    spy = _SnapshotSpyStrategy()
    run_backtest(spy, "TEST", df, config)

    assert spy.seen_snapshots
    assert all(snap["ema9"] is not None for snap in spy.seen_snapshots)


def test_regime_snapshot_series_caches_by_timeframe_and_handles_a_missing_file(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        engine_module, "get_settings", lambda: SimpleNamespace(historical_data_dir=str(tmp_path)),
    )
    engine_module._regime_cache.clear()
    try:
        result = engine_module._regime_snapshot_series(1)
        assert result is None
        assert 1 in engine_module._regime_cache  # "checked, missing" is itself cached
    finally:
        engine_module._regime_cache.clear()
