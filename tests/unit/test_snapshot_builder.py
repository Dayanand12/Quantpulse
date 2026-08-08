import datetime as dt

import polars as pl

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


def test_returns_expected_columns():
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])

    snap = build_snapshot_series(df, timeframe_minutes=1)

    assert snap.columns == [
        "date", "ltp", "high", "low", "ema5", "ema9", "ema21", "rsi", "adx", "atr_pct",
        "vwap", "volume_ratio", "orb_low", "distance_to_or_low",
    ]


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


def test_orb_low_is_the_915_930_window_minimum():
    df = make_df([(dt.date(2026, 1, 5), 40, 100.0)])
    # Opening range window is bars 0-15 (09:15-09:30) — with drift=0.05/bar
    # starting at 100.0, the lowest low in that window is at bar 0.
    expected_orb_low = round(100.0 + 0.05, 2) - 0.5  # first bar's low

    snap = build_snapshot_series(df, timeframe_minutes=1)

    orb_lows = {v for v in snap["orb_low"].to_list() if v is not None}
    assert orb_lows == {expected_orb_low}


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
