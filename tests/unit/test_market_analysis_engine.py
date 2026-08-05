import datetime as dt

import pytest

from services.market_analysis_engine import MarketAnalysisEngine


class FakeZerodhaClient:
    """Stands in for Data_ingestion.client.ZerodhaClient — that class can't
    be constructed in tests without real API credentials / a browser login
    flow, and MarketAnalysisEngine only ever calls these two members."""

    def __init__(self, candles=None, error=None):
        self.exchange = "NSE"
        self._candles = candles or []
        self._error = error

    def fetch_historical_data(self, symbol, interval, from_date, to_date, exchange):
        if self._error:
            raise self._error
        return self._candles


def make_candles(count, start_price=100.0, step=1.0, start=None):
    """count 1-minute candles today, closing price rising by `step` each
    bar — gives a deterministic uptrend so regime classification is
    predictable in assertions."""
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


def test_error_when_fetch_raises():
    engine = MarketAnalysisEngine(FakeZerodhaClient(error=RuntimeError("boom")))

    result = engine.analyze("RELIANCE")

    assert "error" in result


def test_error_when_not_enough_candles():
    engine = MarketAnalysisEngine(FakeZerodhaClient(candles=make_candles(10)))

    result = engine.analyze("RELIANCE")

    assert "error" in result


def test_analyze_computes_indicators_for_uptrend():
    engine = MarketAnalysisEngine(FakeZerodhaClient(candles=make_candles(80)))

    result = engine.analyze("RELIANCE")

    assert "error" not in result
    assert result["symbol"] == "RELIANCE"
    assert result["ltp"] == pytest.approx(100.0 + 79)
    assert result["ema5"] is not None
    assert result["ema9"] is not None
    assert result["ema21"] is not None
    assert result["rsi"] is not None
    assert result["adx"] is not None
    assert result["vwap"] is not None
    # Steady uptrend all session -> latest close sits above the session VWAP.
    assert result["ltp"] > result["vwap"]
    assert result["ema5"] > result["ema9"] > result["ema21"]
    assert result["regime"] == "Bullish Trend"
    assert result["as_of"] is not None


def test_bullish_trend_suggests_buy_side():
    engine = MarketAnalysisEngine(FakeZerodhaClient(candles=make_candles(80, step=1.0)))

    result = engine.analyze("RELIANCE")

    assert result["regime"] == "Bullish Trend"
    assert result["suggested_side"] == "BUY"
    assert result["decision"].startswith("BUY")
    assert "BUY-side" in result["summary"]


def test_bearish_trend_suggests_sell_side():
    # High start price keeps the fixed +/-0.5 high/low offset a tiny
    # fraction of price, so ATR% stays "Compressed" rather than crossing
    # into "High Expansion" (which would force NO TRADE regardless of
    # regime) purely as an artifact of this synthetic data's price level.
    engine = MarketAnalysisEngine(
        FakeZerodhaClient(candles=make_candles(80, start_price=2000.0, step=-1.0))
    )

    result = engine.analyze("RELIANCE")

    assert result["regime"] == "Bearish Trend"
    assert result["suggested_side"] == "SELL"
    assert result["decision"].startswith("SELL")
    assert "SELL-side" in result["summary"]


def test_flat_market_suggests_no_side():
    # No price movement at all -> ADX stays near zero -> Range regime,
    # no side to favor.
    engine = MarketAnalysisEngine(FakeZerodhaClient(candles=make_candles(80, step=0.0)))

    result = engine.analyze("RELIANCE")

    assert result["suggested_side"] is None
    assert result["decision"] == "NO TRADE"
    assert "don't favor either side" in result["summary"]


def test_analyze_reports_none_vwap_when_no_candles_fall_today():
    yesterday = dt.datetime.combine(
        dt.date.today() - dt.timedelta(days=1), dt.time(9, 15)
    )
    engine = MarketAnalysisEngine(
        FakeZerodhaClient(candles=make_candles(80, start=yesterday))
    )

    result = engine.analyze("RELIANCE")

    assert "error" not in result
    assert result["vwap"] is None
    # Classification degrades gracefully (vwap treated as 0) rather than raising.
    assert result["regime"] in {"Bullish Trend", "Range", "Transition", "Bearish Trend"}
