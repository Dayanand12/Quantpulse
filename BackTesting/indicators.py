import polars as pl
import numpy as np
import talib

import talib

class IndicatorCalculator:
    def __init__(self, history):
        self.history = history
    @staticmethod
    def rsi(symbol, df, period=14):
        RSI = {}
        rsi = talib.RSI(df["close"], timeperiod=period)
        rsi = rsi.dropna()  # drop NaN values
        if len(rsi) > 1:  # ensure enough values
            RSI[symbol] = rsi.iloc[-1]  # return previous RSI
        return RSI

    @staticmethod
    def ema(symbol, df, period=14):
        EMA = {}
        ema = talib.EMA(df["close"], timeperiod=period)
        ema = ema.dropna()  # drop NaN values
        if len(ema) > 1:  # ensure enough values
            EMA[symbol] = ema.iloc[-1]
        return EMA

    import talib

class IndicatorCalculator:
    def __init__(self, history):
        self.history = history

    @staticmethod
    def rsi(symbol, df, period=14):
        RSI = {}
        rsi = talib.RSI(df["close"], timeperiod=period)
        rsi = rsi.dropna()
        if len(rsi) > 1:
            RSI[symbol] = rsi.iloc[-1]
        return RSI

    @staticmethod
    def ema(symbol, df, period=14):
        EMA = {}
        ema = talib.EMA(df["close"], timeperiod=period)
        ema = ema.dropna()
        if len(ema) > 1:
            EMA[symbol] = ema.iloc[-1]
        return EMA

    @staticmethod
    def macd(symbol, df, fastperiod=12, slowperiod=26, signalperiod=9):
        MACD = {}
        macd, macdsignal, macdhist = talib.MACD(
            df["close"],
            fastperiod=fastperiod,
            slowperiod=slowperiod,
            signalperiod=signalperiod,
        )
        macd = macd.dropna()
        macdsignal = macdsignal.dropna()
        macdhist = macdhist.dropna()

        if len(macd) > 1 and len(macdsignal) > 1 and len(macdhist) > 1:
            MACD[symbol] = {
                "macd": macd.iloc[-1],
                "signal": macdsignal.iloc[-1],
                "hist": macdhist.iloc[-1],
            }
        return MACD


    @staticmethod
    def adx(symbol, df, period=14):
        ADX = {}
        adx = talib.ADX(df["high"], df["low"], df["close"], timeperiod=period)
        adx = adx.dropna()
        if len(adx) > 1:
            ADX[symbol] = adx.iloc[-1]
        return ADX

    @staticmethod
    def atr(symbol, df, period=14):
        ATR = {}
        atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=period)
        atr = atr.dropna()
        if len(atr) > 1:
            ATR[symbol] = atr.iloc[-1]
        return ATR

    @staticmethod
    def vwap(symbol, df):
        VWAP = {}
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cum_pv = (typical_price * df["volume"]).cumsum()
        cum_vol = df["volume"].cumsum()
        if cum_vol.iloc[-1] > 0:
            VWAP[symbol] = float(cum_pv.iloc[-2] / cum_vol.iloc[-1])
        return VWAP

    @staticmethod
    def orb(symbol, df, N=3):
        ORB = {}
        orb_high = max(df["high"][:N])
        orb_low = min(df["low"][:N])
        ORB[symbol] = {"high": float(orb_high), "low": float(orb_low)}
        return ORB
