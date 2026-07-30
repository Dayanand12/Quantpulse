# backend/market_analysis_engine.py
"""On-demand market analysis for ANY tradeable symbol — not limited to the
watchlist (unlike the live tick cache ITradingEngine.get_snapshot() reads
from, which only has data for symbols the Zerodha WebSocket happens to be
subscribed to right now).

Pulls recent 1-minute historical candles straight from Kite — the same
timeframe live/candle_builder.py builds its own candles from — and runs
them through the same backtest/indicators.py calculator live/live_engine.py
uses, so the numbers here are directly comparable to what Zerodha's own
chart shows for the same symbol/timeframe. Returns both the raw indicator
values (for that comparison) and the interpreted regime/decision verdict
the Market Analysis page already showed before this existed.
"""

import datetime as dt
import math

import polars as pl

from backtest.indicators import IndicatorCalculator

# Calendar days of 1-minute history to fetch. Comfortably covers weekends/
# holidays and gives EMA21/ADX14/ATR14 enough bars to have converged by
# "now" — an indicator seeded too close to the present reads noticeably
# different from Zerodha's own long-warmed-up chart, which is exactly the
# mismatch this feature exists to avoid.
_LOOKBACK_DAYS = 10

# Below this many candles, EMA21/ADX14 haven't fully warmed up (TA-Lib
# returns NaN until then) — report "not enough data" instead of a
# misleadingly-partial number.
_MIN_CANDLES = 50

# Kite returns tz-aware IST timestamps, but polars normalizes datetime
# columns to UTC internally (Datetime(time_zone='UTC')) — a value that's
# still the correct instant, but displays 5:30 off if formatted without
# converting back. Zerodha's own chart always shows IST, so that's what
# "as_of" needs to match.
_IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _clean(value):
    """talib returns NaN (not None) for not-yet-warmed-up bars — treat
    both as "no value yet" rather than let NaN leak into an API response."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _classify(ltp, ema9, ema21, adx, vwap, atr_pct):
    """Same regime/trend/volatility heuristic this engine always used,
    plus a side-aware decision — factored out so analyze() calls it once,
    not inline.

    decision/suggested_side are BUY-or-SELL aware (not SELL-only like the
    original ORB-era version): the app now runs both BUY-side (EMA
    Crossover) and SELL-side (ORB Reversal) strategies, so "what to do
    today" has to reflect whichever side the regime actually favors, not
    always assume short.
    """
    ema9 = ema9 or 0
    ema21 = ema21 or 0
    adx = adx or 0
    vwap = vwap or 0
    atr_pct = atr_pct or 0

    if ema9 > ema21 and ltp > vwap:
        regime = "Bullish Trend"
    elif ema9 < ema21 and ltp < vwap:
        regime = "Bearish Trend"
    elif adx < 18:
        regime = "Range"
    else:
        regime = "Transition"

    if adx > 25:
        trend_strength = "Strong"
    elif adx > 20:
        trend_strength = "Moderate"
    else:
        trend_strength = "Weak"

    if atr_pct > 1.2:
        volatility_state = "High Expansion"
    elif atr_pct < 0.5:
        volatility_state = "Compressed"
    else:
        volatility_state = "Normal"

    score = 0
    if regime in ("Bullish Trend", "Bearish Trend"):
        score += 3
    elif regime == "Range":
        score += 2

    if trend_strength == "Strong":
        score += 2
    elif trend_strength == "Moderate":
        score += 1

    if volatility_state == "Normal":
        score += 2
    elif volatility_state == "Compressed":
        score += 1

    if volatility_state == "High Expansion" or score < 4 or regime not in (
        "Bullish Trend", "Bearish Trend"
    ):
        decision = "NO TRADE"
        suggested_side = None
    else:
        side = "BUY" if regime == "Bullish Trend" else "SELL"
        size = "NORMAL SIZE" if score >= 7 else "REDUCED SIZE"
        decision = f"{side} {size}"
        suggested_side = side

    return {
        "regime": regime,
        "trend_strength": trend_strength,
        "volatility_state": volatility_state,
        "confidence_score": score,
        "decision": decision,
        "suggested_side": suggested_side,
        "summary": _summary(regime, trend_strength, volatility_state, decision, suggested_side),
    }


def _summary(regime, trend_strength, volatility_state, decision, suggested_side):
    base = f"{trend_strength} {regime.lower()}, {volatility_state.lower()} volatility."

    if suggested_side is None:
        action = "Conditions don't favor either side right now — sit out or wait for a clearer setup."
    else:
        size = "full size" if "NORMAL" in decision else "reduced size"
        action = f"Favors {suggested_side}-side strategies today, at {size}."

    return f"{base} {action}"


class MarketAnalysisEngine:
    def __init__(self, zerodha_client):
        self.zerodha_client = zerodha_client

    def analyze(self, symbol: str) -> dict:
        now = dt.datetime.now()

        try:
            candles = self.zerodha_client.fetch_historical_data(
                symbol=symbol,
                interval="minute",
                from_date=now - dt.timedelta(days=_LOOKBACK_DAYS),
                to_date=now,
                exchange=self.zerodha_client.exchange,
            )
        except Exception as e:
            return {"error": f"Could not fetch data for {symbol}: {e}"}

        if not candles or len(candles) < _MIN_CANDLES:
            return {"error": f"Not enough historical data yet for {symbol}."}

        df = pl.DataFrame(candles).select(["date", "open", "high", "low", "close", "volume"])
        df = df.sort("date")

        df = df.with_columns([
            IndicatorCalculator.ema(df, period=5),
            IndicatorCalculator.ema(df, period=9),
            IndicatorCalculator.ema(df, period=21),
            IndicatorCalculator.rsi(df, period=14),
            IndicatorCalculator.adx(df, period=14),
            IndicatorCalculator.atr(df, period=14),
        ])
        latest = df.row(-1, named=True)

        ltp = _clean(latest["close"]) or 0.0
        ema5 = _clean(latest["EMA_5"])
        ema9 = _clean(latest["EMA_9"])
        ema21 = _clean(latest["EMA_21"])
        rsi = _clean(latest["RSI_14"])
        adx = _clean(latest["ADX_14"])
        atr = _clean(latest["ATR_14"])
        atr_pct = (atr / ltp) * 100 if atr is not None and ltp else None

        today = now.date()
        session_df = df.filter(pl.col("date").dt.date() == today)
        total_volume = session_df["volume"].sum() if session_df.height else 0
        vwap = (
            _clean((session_df["close"] * session_df["volume"]).sum() / total_volume)
            if total_volume
            else None
        )

        last_volume = df["volume"][-1]
        avg_volume = df["volume"][-20:].mean()
        volume_ratio = _clean(last_volume / avg_volume) if avg_volume else None

        as_of = latest["date"]
        as_of_ist = as_of.astimezone(_IST) if as_of and as_of.tzinfo else as_of

        return {
            "symbol": symbol,
            "time": now.strftime("%H:%M:%S"),
            # The most recent CLOSED 1-min candle this was computed from,
            # in IST — Zerodha's chart also folds in the still-forming
            # current candle, so compare against this timestamp, not
            # "right now", for numbers that should actually line up.
            "as_of": as_of_ist.strftime("%Y-%m-%d %H:%M:%S") if as_of_ist else None,
            "ltp": ltp,
            "ema5": ema5,
            "ema9": ema9,
            "ema21": ema21,
            "rsi": rsi,
            "adx": adx,
            "atr_pct": atr_pct,
            "vwap": vwap,
            "volume_ratio": volume_ratio,
            **_classify(ltp, ema9, ema21, adx, vwap, atr_pct),
        }
