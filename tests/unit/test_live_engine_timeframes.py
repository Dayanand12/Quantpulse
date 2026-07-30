import datetime as dt

import polars as pl

from live.live_engine import LiveEngine, SUPPORTED_TIMEFRAMES


def make_1min_df(count, start=None, start_price=100.0, step=1.0):
    """Synthetic 1-minute OHLCV frame starting at the exchange session
    open (09:15), matching the shape live/live_engine.py builds from
    live ticks / warm-start candles."""
    start = start or dt.datetime.combine(dt.date.today(), dt.time(9, 15))
    rows = []
    price = start_price
    for i in range(count):
        d = start + dt.timedelta(minutes=i)
        rows.append({
            "date": d, "open": price, "high": price + 0.5, "low": price - 0.5,
            "close": price, "volume": 10.0,
        })
        price += step
    return pl.DataFrame(
        rows,
        schema={
            "date": pl.Datetime, "open": pl.Float64, "high": pl.Float64,
            "low": pl.Float64, "close": pl.Float64, "volume": pl.Float64,
        },
    )


def make_candles(count, start=None, start_price=100.0, step=1.0):
    """Same series as make_1min_df, but as the list-of-dicts shape
    LiveEngine.warm_start()/on_new_candle() actually consume."""
    df = make_1min_df(count, start, start_price, step)
    return df.to_dicts()


# ---------------------------------------------------------------------------
# Resampling correctness — the highest-risk new logic in this feature.
# Expected values below were independently verified against a standalone
# script before being written into live/live_engine.py (see
# docs/plans/per-strategy-timeframes.md); asserted here to catch any
# future regression in the bucket-alignment math.
# ---------------------------------------------------------------------------


def test_resample_1_minute_is_unchanged():
    df = make_1min_df(10)

    out = LiveEngine._resample(df, 1)

    assert out is df


def test_resample_5_minute_aligns_to_session_open_and_aggregates_ohlcv():
    df = make_1min_df(23)  # 09:15 .. 09:37

    out = LiveEngine._resample(df, 5)

    starts = [row["date"].strftime("%H:%M") for row in out.iter_rows(named=True)]
    assert starts == ["09:15", "09:20", "09:25", "09:30", "09:35"]

    first = out.row(0, named=True)
    # 09:15-09:19: prices 100..104 -> open=first, high=max+0.5, low=min-0.5, close=last, volume=sum
    assert first["open"] == 100.0
    assert first["high"] == 104.5
    assert first["low"] == 99.5
    assert first["close"] == 104.0
    assert first["volume"] == 50.0

    last = out.row(-1, named=True)  # partial, still-forming bucket by design
    assert last["date"].strftime("%H:%M") == "09:35"
    assert last["open"] == 120.0
    assert last["close"] == 122.0
    assert last["volume"] == 30.0  # only 09:35-09:37 exist so far (3 bars)


def test_resample_10_minute_does_not_evenly_divide_the_hour_but_still_aligns():
    # 10 doesn't divide 60 -> a real risk that bucketing from midnight
    # (rather than from the 09:15 session open) would misalign these.
    df = make_1min_df(23)

    out = LiveEngine._resample(df, 10)

    starts = [row["date"].strftime("%H:%M") for row in out.iter_rows(named=True)]
    assert starts == ["09:15", "09:25", "09:35"]


def test_resample_15_minute_matches_the_orb_opening_range_window():
    # 09:15-09:30 is exactly one 15-minute bucket -- the same window
    # live/live_engine.py's OR logic uses, independently of timeframe.
    df = make_1min_df(23)

    out = LiveEngine._resample(df, 15)

    starts = [row["date"].strftime("%H:%M") for row in out.iter_rows(named=True)]
    assert starts == ["09:15", "09:30"]
    assert out.row(0, named=True)["volume"] == 150.0  # 15 one-min bars


def test_resample_30_minute():
    df = make_1min_df(23)

    out = LiveEngine._resample(df, 30)

    assert out.height == 1
    assert out.row(0, named=True)["date"].strftime("%H:%M") == "09:15"


# ---------------------------------------------------------------------------
# LiveEngine integration: per-timeframe snapshot behavior
# ---------------------------------------------------------------------------


def test_supported_timeframes_includes_every_documented_option():
    assert set(SUPPORTED_TIMEFRAMES) == {
        "minute", "3minute", "5minute", "10minute", "15minute", "30minute",
    }
    assert SUPPORTED_TIMEFRAMES["minute"] == 1
    assert SUPPORTED_TIMEFRAMES["30minute"] == 30


def test_higher_timeframe_needs_proportionally_more_bars_before_it_appears():
    # 150 one-minute candles -> 150 minute-bars (>=25), 30 five-min bars
    # (>=25), but only 15 ten-min bars (<25) -- the 10-minute timeframe
    # must not have a snapshot yet even though 1-minute and 5-minute do.
    engine = LiveEngine(["TCS"], capital=100_000)

    engine.warm_start("TCS", make_candles(150))

    assert "TCS" in engine.get_snapshot("minute")
    assert "TCS" in engine.get_snapshot("5minute")
    assert "TCS" not in engine.get_snapshot("10minute")
    assert "TCS" not in engine.get_snapshot("15minute")
    assert "TCS" not in engine.get_snapshot("30minute")


def test_get_snapshot_default_matches_explicit_minute_timeframe():
    engine = LiveEngine(["TCS"], capital=100_000)
    engine.warm_start("TCS", make_candles(40))

    assert engine.get_snapshot() == engine.get_snapshot("minute")


def test_different_timeframes_produce_independent_indicator_values():
    engine = LiveEngine(["TCS"], capital=100_000)
    engine.warm_start("TCS", make_candles(150))

    minute_snapshot = engine.get_snapshot("minute")["TCS"]
    five_min_snapshot = engine.get_snapshot("5minute")["TCS"]

    # Same underlying data, different bar size -> different EMA reading.
    assert minute_snapshot["ema9"] != five_min_snapshot["ema9"]
    # Both should agree on the latest close, though (last price is last
    # price regardless of how it's bucketed).
    assert minute_snapshot["ltp"] == five_min_snapshot["ltp"]


def test_opening_range_is_shared_across_every_timeframe():
    # OR is wall-clock (9:15-9:30) tracking off the raw 1-minute candles,
    # not resampling-dependent -- every timeframe with a snapshot at all
    # should report the identical orb_low.
    engine = LiveEngine(["TCS"], capital=100_000)
    engine.warm_start("TCS", make_candles(150))

    minute_orb_low = engine.get_snapshot("minute")["TCS"]["orb_low"]
    five_min_orb_low = engine.get_snapshot("5minute")["TCS"]["orb_low"]

    assert minute_orb_low is not None
    assert minute_orb_low == five_min_orb_low
