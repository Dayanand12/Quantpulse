import polars as pl
import talib
import numpy as np
class IndicatorCalculator:
    @staticmethod
    def ema(df: pl.DataFrame, col="close", period=9):
        return pl.Series(f"EMA_{period}", talib.EMA(df[col].to_numpy(), timeperiod=period))

    @staticmethod
    def rsi(df: pl.DataFrame, col="close", period=14):
        return pl.Series(f"RSI_{period}", talib.RSI(df[col].to_numpy(), timeperiod=period))

    @staticmethod
    def rsi_ma(df: pl.DataFrame, col="close", rsi_period=14, ma_period=20):
        rsi_series = talib.RSI(df[col].to_numpy(), timeperiod=rsi_period)
        rsi_ma = talib.EMA(rsi_series, timeperiod=ma_period)
        return pl.Series(f"RSI_MA_{rsi_period}_{ma_period}", rsi_ma)

    @staticmethod
    def adx(df: pl.DataFrame, period=14):
        return pl.Series(f"ADX_{period}", talib.ADX(df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy(), timeperiod=period))

    @staticmethod
    def atr(df: pl.DataFrame, period=14):
        return pl.Series(f"ATR_{period}", talib.ATR(df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy(), timeperiod=period))

    @staticmethod
    def opening_range_high(df: pl.DataFrame, minutes=5):
        df = df.with_columns(pl.col("date").dt.date().alias("date_only"))
        orb_highs = []
        current_day = None
        for row in df.iter_rows(named=True):
            day = row["date_only"]
            if day != current_day:
                current_day = day
                day_data = df.filter(pl.col("date_only") == current_day)
                orb_high = day_data.head(minutes)["high"].max()
            orb_highs.append(orb_high)
        return pl.Series("ORB_High", orb_highs)
