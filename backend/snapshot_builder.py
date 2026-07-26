# backend/snapshot_builder.py

import numpy as np
import talib
from threading import Lock

class SnapshotBuilder:
    def __init__(self, candle_builder, or_manager):
        self.candle_builder = candle_builder
        self.or_manager = or_manager
        self.snapshot = {}
        self.lock = Lock()

    def update(self, symbol):
        candles = self.candle_builder.get_history(symbol)

        if len(candles) < 25:
            return

        close = np.array([c["close"] for c in candles])
        high = np.array([c["high"] for c in candles])
        low = np.array([c["low"] for c in candles])
        volume = np.array([c["volume"] for c in candles])

        ema9 = talib.EMA(close, 9)[-1]
        ema21 = talib.EMA(close, 21)[-1]
        rsi = talib.RSI(close, 14)[-1]
        adx = talib.ADX(high, low, close, 14)[-1]
        atr = talib.ATR(high, low, close, 14)[-1]

        vwap = np.sum(close * volume) / np.sum(volume)
        vol_ratio = volume[-1] / np.mean(volume[-20:])

        or_data = self.or_manager.get_or(symbol)
        if not or_data or not or_data["locked"]:
            return

        ltp = close[-1]
        orb_low = or_data["low"]
        distance = ((ltp - orb_low) / orb_low) * 100

        atr_pct = (atr / ltp) * 100

        with self.lock:
            self.snapshot[symbol] = {
                "ltp": float(ltp),
                "ema9": float(ema9),
                "ema21": float(ema21),
                "rsi": float(rsi),
                "adx": float(adx),
                "vwap": float(vwap),
                "volume_ratio": float(vol_ratio),
                "atr_pct": float(atr_pct),
                "orb_low": float(orb_low),
                "distance_to_or_low": float(distance)
            }

    def get_snapshot(self):
        with self.lock:
            return dict(self.snapshot)