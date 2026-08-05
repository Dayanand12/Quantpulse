import datetime as dt

from runners.paper_trading.warm_start import warm_start_indicators


class FakeZerodhaClient:
    def __init__(self, candles_by_symbol=None, raise_for=None):
        self.exchange = "NSE"
        self._candles_by_symbol = candles_by_symbol or {}
        self._raise_for = raise_for or set()

    def fetch_historical_data(self, symbol, interval, from_date, to_date, exchange):
        if symbol in self._raise_for:
            raise RuntimeError("boom")
        return self._candles_by_symbol.get(symbol, [])


class FakeLiveEngine:
    def __init__(self):
        self.warm_started = {}

    def warm_start(self, symbol, candles):
        self.warm_started[symbol] = candles


def test_warm_starts_every_symbol_with_fetched_candles():
    candles = {
        "TCS": [{"date": dt.datetime.now()}],
        "INFY": [{"date": dt.datetime.now()}],
    }
    client = FakeZerodhaClient(candles_by_symbol=candles)
    engine = FakeLiveEngine()

    warm_start_indicators(engine, client, ["TCS", "INFY"], "NSE")

    assert engine.warm_started["TCS"] == candles["TCS"]
    assert engine.warm_started["INFY"] == candles["INFY"]


def test_skips_symbol_with_no_candles_returned():
    client = FakeZerodhaClient(candles_by_symbol={"TCS": []})
    engine = FakeLiveEngine()

    warm_start_indicators(engine, client, ["TCS"], "NSE")

    assert "TCS" not in engine.warm_started


def test_one_symbol_failing_does_not_block_the_others():
    client = FakeZerodhaClient(
        candles_by_symbol={"INFY": [{"date": dt.datetime.now()}]},
        raise_for={"TCS"},
    )
    engine = FakeLiveEngine()

    warm_start_indicators(engine, client, ["TCS", "INFY"], "NSE")

    assert "TCS" not in engine.warm_started
    assert "INFY" in engine.warm_started


def test_no_symbols_is_a_noop():
    client = FakeZerodhaClient()
    engine = FakeLiveEngine()

    warm_start_indicators(engine, client, [], "NSE")

    assert engine.warm_started == {}
