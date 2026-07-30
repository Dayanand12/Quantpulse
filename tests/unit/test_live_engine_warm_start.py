import datetime as dt

from live.live_engine import LiveEngine


def make_candles(count, start=None, start_price=100.0, step=0.1, tz=None):
    start = start or dt.datetime.combine(dt.date.today(), dt.time(9, 15))
    candles = []
    price = start_price
    for i in range(count):
        date = start + dt.timedelta(minutes=i)
        if tz is not None:
            date = date.replace(tzinfo=tz)
        candles.append({
            "date": date,
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 1000,
        })
        price += step
    return candles


def test_warm_start_populates_indicator_snapshot():
    engine = LiveEngine(["TCS"], capital=100_000)

    engine.warm_start("TCS", make_candles(40))

    snapshot = engine.get_snapshot()
    assert "TCS" in snapshot
    assert snapshot["TCS"]["ema9"] is not None
    assert snapshot["TCS"]["ltp"] is not None


def test_warm_start_too_few_candles_leaves_snapshot_empty():
    engine = LiveEngine(["TCS"], capital=100_000)

    engine.warm_start("TCS", make_candles(10))

    assert engine.get_snapshot() == {}


def test_warm_start_captures_opening_range_from_9_15_to_9_30():
    engine = LiveEngine(["TCS"], capital=100_000)

    # 40 candles starting 09:15 -> covers the 9:15-9:30 OR window plus
    # enough bars afterward for indicators to populate.
    engine.warm_start("TCS", make_candles(40))

    snapshot = engine.get_snapshot()
    assert snapshot["TCS"]["orb_low"] is not None
    assert engine.or_data["TCS"]["locked"] is True


def test_warm_start_strips_timezone_without_raising():
    engine = LiveEngine(["TCS"], capital=100_000)
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))

    # Must not raise: polars would otherwise reject concatenating naive
    # and tz-aware Datetime columns across successive on_new_candle calls.
    engine.warm_start("TCS", make_candles(30, tz=ist))

    last_date = engine.data["TCS"]["date"][-1]
    assert last_date.tzinfo is None


def test_warm_start_then_live_ticks_share_the_same_naive_column():
    # The realistic sequence: warm-start at startup, then real ticks
    # arrive via process_tick (live/candle_builder.py — always naive
    # local time). Must not raise when the two are concatenated together.
    engine = LiveEngine(["TCS"], capital=100_000)
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    engine.warm_start("TCS", make_candles(30, tz=ist))

    engine.on_new_candle("TCS", {
        "date": dt.datetime.now().replace(second=0, microsecond=0),
        "open": 103.0, "high": 103.5, "low": 102.5, "close": 103.0, "volume": 1000,
    })

    assert engine.data["TCS"].height == 31
