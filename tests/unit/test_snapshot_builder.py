import datetime as dt

import polars as pl
import talib

from core.domain.indicator_registry import IndicatorSpec
from runners.backtesting.snapshot_builder import build_snapshot_series


def _synthetic_day(day: dt.date, n_bars: int, start_price: float, drift: float = 0.05):
    rows = []
    price = start_price
    minute = 0
    for i in range(n_bars):
        # Skip the lunch-hour-sized gap for realism? Not needed — every bar
        # 09:15, 09:16, ... is fine for indicator warm-up purposes.
        ts = dt.datetime.combine(day, dt.time(9, 15)) + dt.timedelta(minutes=minute)
        price = round(price + drift, 2)
        rows.append({
            "date": ts,
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 1000.0 + i * 10,
        })
        minute += 1
    return rows


def make_df(days_and_bars):
    """days_and_bars: list of (date, n_bars, start_price)."""
    rows = []
    for day, n_bars, start_price in days_and_bars:
        rows.extend(_synthetic_day(day, n_bars, start_price))
    return pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Datetime))


def make_option_df(days_and_bars):
    """Same as make_df but with an `oi` column present — mirrors
    historical_loader.load_option_csv's shape, oi rising 100 per bar so
    each bucket's `.last()` is distinguishable from its neighbors."""
    df = make_df(days_and_bars)
    return df.with_columns((pl.arange(0, df.height).cast(pl.Float64) * 100 + 5000).alias("oi"))


def test_returns_expected_columns():
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=1)

    assert snap.columns == [
        "date", "ltp", "high", "low", "ema5", "ema9", "ema21", "rsi", "adx", "atr_pct",
        "vwap", "volume_ratio", "orb_low", "orb_high", "distance_to_or_low", "oi",
    ]
    # No `oi` column in the input (equity data) -> always None in the output.
    assert snap["oi"].null_count() == snap.height


def test_drops_warmup_bars_below_minimum():
    # Fewer than 25 bars total -> live_engine parity: no snapshot at all.
    df = make_df([(dt.date(2026, 1, 5), 20, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=1)

    assert snap.height == 0


def test_keeps_bars_from_the_25th_onward():
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=1)

    # 40 bars in, first 24 dropped (matches live_engine's `if df.height < 25`)
    assert snap.height == 40 - 24


def test_distance_to_or_low_is_none_until_after_930():
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=1)

    for row in snap.iter_rows(named=True):
        if row["date"].time() <= dt.time(9, 30):
            assert row["distance_to_or_low"] is None
        else:
            assert row["distance_to_or_low"] is not None


def test_orb_high_is_none_until_after_930():
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=1)

    for row in snap.iter_rows(named=True):
        if row["date"].time() <= dt.time(9, 30):
            assert row["orb_high"] is None
        else:
            assert row["orb_high"] is not None


def test_orb_high_is_the_915_930_window_maximum():
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])
    # Opening range window is bars 0-15 (09:15-09:30) — with drift=0.05/bar
    # starting at 100.0, the highest high in that window is at bar 15.
    expected_orb_high = round(100.0 + 0.05 * 16, 2) + 0.5  # bar 15's high

    snap = build_snapshot_series(df, timeframe_minutes=1)

    orb_highs = {v for v in snap["orb_high"].to_list() if v is not None}
    assert orb_highs == {expected_orb_high}


def test_orb_low_is_the_915_930_window_minimum():
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])
    # Opening range window is bars 0-15 (09:15-09:30) — with drift=0.05/bar
    # starting at 100.0, the lowest low in that window is at bar 0.
    expected_orb_low = round(100.0 + 0.05, 2) - 0.5  # first bar's low

    snap = build_snapshot_series(df, timeframe_minutes=1)

    orb_lows = {v for v in snap["orb_low"].to_list() if v is not None}
    assert orb_lows == {expected_orb_low}


def test_orb_low_is_none_until_after_930():
    # A hard breakout condition against orb_low (e.g. torb_breakout_short)
    # would otherwise see the FINAL opening-range low leak into bars from
    # 9:15-9:29 — this aggregate is computed as one batch over the whole
    # 9:15-9:30 window, so without masking it's known before it's actually
    # finished forming (impossible live, where it's only known
    # incrementally as candles arrive).
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=1)

    for row in snap.iter_rows(named=True):
        if row["date"].time() <= dt.time(9, 30):
            assert row["orb_low"] is None
        else:
            assert row["orb_low"] is not None


def test_vwap_resets_per_session():
    df = make_df([
        (dt.date(2026, 1, 5), 40, 100.0),
        (dt.date(2026, 1, 6), 40, 500.0),  # very different price level
    ])

    snap = build_snapshot_series(df, timeframe_minutes=1)

    day1_vwaps = [r["vwap"] for r in snap.iter_rows(named=True) if r["date"].date() == dt.date(2026, 1, 5)]
    day2_vwaps = [r["vwap"] for r in snap.iter_rows(named=True) if r["date"].date() == dt.date(2026, 1, 6)]

    # Day 2's VWAP must track day 2's own (much higher) price level, not
    # carry over day 1's — proves the cumulative sum resets per session.
    assert max(day1_vwaps) < min(day2_vwaps)


def test_extra_indicators_are_additive_not_replacing_the_fixed_set():
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=1, extra_indicators=[IndicatorSpec.of("ema", period=20)])

    assert "ema_20" in snap.columns
    # every fixed column from the no-extra-indicators case must still be there
    assert {"ltp", "ema5", "ema9", "ema21", "rsi", "adx", "atr_pct", "vwap", "volume_ratio"} <= set(snap.columns)


def test_extra_indicator_values_match_an_independent_talib_calculation():
    df = make_df([(dt.date(2026, 1, 5), 60, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=1, extra_indicators=[IndicatorSpec.of("ema", period=20)])

    # Independent recomputation over the FULL base df's close series (same
    # convention every indicator in this pipeline already follows), then
    # compare at the last bar only — proves the registry-computed value is
    # correct, not just present.
    independent = talib.EMA(df["close"].to_numpy(), timeperiod=20)
    assert snap["ema_20"][-1] == independent[-1]


def test_no_extra_indicators_leaves_columns_unchanged():
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])

    with_none = build_snapshot_series(df, timeframe_minutes=1)
    with_empty_list = build_snapshot_series(df, timeframe_minutes=1, extra_indicators=[])

    assert with_none.columns == with_empty_list.columns


def test_extra_indicators_present_even_when_below_warmup_minimum():
    # Fewer than 25 bars -> the early-return branch must still include the
    # requested extra columns (as None), or the caller's later .select()
    # on a real (>=25 bar) run would KeyError on a column that sometimes
    # exists and sometimes doesn't.
    df = make_df([(dt.date(2026, 1, 5), 20, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=1, extra_indicators=[IndicatorSpec.of("ema", period=20)])

    assert "ema_20" in snap.columns
    assert snap.height == 0


def test_oi_passes_through_at_1minute():
    df = make_option_df([(dt.date(2026, 1, 5), 40, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=1)

    # 1-minute bars: each row's oi is exactly that bar's own raw oi value
    # (base_df["oi"][24:], since the first 24 warm-up bars are dropped).
    expected = df["oi"].to_list()[24:]
    assert snap["oi"].to_list() == expected


def test_oi_resamples_with_last_value_per_bucket():
    # 150 bars of 1-minute data (30 five-minute buckets) with oi rising
    # every bar -> resampling to 5-minute buckets should carry each
    # bucket's LAST raw oi value, same 09:15-aligned bucket boundaries
    # LiveEngine._resample uses, not an average or a first-value pick.
    # The first 24 buckets are dropped by the _MIN_BARS warm-up, so the
    # first surviving output row is bucket index 24: raw minute-offsets
    # 120-124, whose last is raw_oi[124].
    df = make_option_df([(dt.date(2026, 1, 5), 150, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=5)

    raw_oi = df["oi"].to_list()
    first_bucket_oi = snap["oi"].to_list()[0]
    assert first_bucket_oi == raw_oi[124]


def test_oi_is_none_when_source_has_no_oi_column():
    # Equity data (no oi column at all) -> oi is always None in the
    # output, never a missing column, so callers never need to branch.
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=5)

    assert snap["oi"].null_count() == snap.height
