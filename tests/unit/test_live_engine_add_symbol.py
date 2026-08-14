import datetime as dt

from runners.paper_trading.live_engine import LiveEngine


def make_candles(count, start=None, start_price=100.0, step=0.1):
    start = start or dt.datetime.combine(dt.date.today(), dt.time(9, 15))
    candles = []
    price = start_price
    for i in range(count):
        candles.append({
            "date": start + dt.timedelta(minutes=i),
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 1000,
        })
        price += step
    return candles


def test_add_symbol_seeds_data_and_or_data_slots():
    engine = LiveEngine(["TCS"], capital=100_000)

    engine.add_symbol("INFY")

    assert "INFY" in engine.data
    assert engine.data["INFY"].height == 0
    assert engine.or_data["INFY"] == {"high": None, "low": None, "locked": False, "date": None}
    assert "INFY" in engine.symbols


def test_add_symbol_is_a_no_op_for_an_already_tracked_symbol():
    engine = LiveEngine(["TCS"], capital=100_000)
    engine.warm_start("TCS", make_candles(30))
    original_data = engine.data["TCS"]

    engine.add_symbol("TCS")

    assert engine.data["TCS"] is original_data
    assert engine.symbols.count("TCS") == 1


def test_add_symbol_then_process_tick_and_warm_start_work_normally():
    engine = LiveEngine(["TCS"], capital=100_000)

    engine.add_symbol("INFY")
    engine.warm_start("INFY", make_candles(30))

    snapshot = engine.get_snapshot()
    assert "INFY" in snapshot
    assert snapshot["INFY"]["ltp"] is not None
    # The originally-constructed symbol is untouched by adding a new one.
    assert "TCS" in engine.data
    assert "TCS" not in snapshot  # never warm-started/ticked in this test


def test_get_snapshot_does_not_include_newly_added_symbol_before_warm_start_or_ticks():
    engine = LiveEngine(["TCS"], capital=100_000)

    engine.add_symbol("INFY")

    # Slots exist, but no candle has been ingested yet — get_snapshot only
    # returns symbols with an actual computed indicator snapshot.
    assert "INFY" not in engine.get_snapshot()
