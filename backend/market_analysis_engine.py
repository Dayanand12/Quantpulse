# backend/market_analysis_engine.py

import datetime as dt

from core.application.interfaces.trading_engine import ITradingEngine


class MarketAnalysisEngine:

    def __init__(self, trading_engine: ITradingEngine):
        self.trading_engine = trading_engine

    def analyze(self, index_symbol):

        snapshot = self.trading_engine.get_snapshot()
        data = snapshot.get(index_symbol)

        if not data:
            return {"error": "No data yet."}

        ltp = data.ltp or 0
        ema9 = data.ema9 or 0
        ema21 = data.ema21 or 0
        adx = data.adx or 0
        vwap = data.vwap or 0
        atr_pct = data.atr_pct or 0

        now_time = dt.datetime.now().strftime("%H:%M:%S")

        # ------------------------
        # STRUCTURE
        # ------------------------
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

        # ------------------------
        # VOLATILITY
        # ------------------------
        if atr_pct > 1.2:
            volatility_state = "High Expansion"
        elif atr_pct < 0.5:
            volatility_state = "Compressed"
        else:
            volatility_state = "Normal"

        # ------------------------
        # CONFIDENCE SCORE
        # ------------------------
        score = 0

        if regime in ["Bullish Trend", "Bearish Trend"]:
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

        # ------------------------
        # FINAL DECISION
        # ------------------------
        if volatility_state == "High Expansion" or score < 4 or regime == "Transition":
            decision = "NO TRADE"
        elif score >= 7:
            decision = "SELL NORMAL SIZE"
        else:
            decision = "SELL REDUCED SIZE"

        return {
            "time": now_time,
            "regime": regime,
            "trend_strength": trend_strength,
            "volatility_state": volatility_state,
            "confidence_score": score,
            "decision": decision,
            "atr_pct": atr_pct
        }