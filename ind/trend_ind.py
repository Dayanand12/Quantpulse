import polars as pl
import numpy as np
from numba import njit

# =========================
# Moving Averages
# =========================
def sma(df: pl.DataFrame, period: int, col: str = "close") -> pl.Series:
    return df.select(pl.col(col).rolling_mean(period)).to_series()

def ema(df: pl.DataFrame, period: int, col: str = "close") -> pl.Series:
    return df.select(pl.col(col).ewm_mean(span=period)).to_series()

# =========================
# RSI (Relative Strength Index)
# =========================
def rsi(df: pl.DataFrame, period: int = 14, col: str = "close") -> pl.Series:
    close = df[col].to_numpy()
    delta = np.diff(close, prepend=close[0])
    up = np.where(delta > 0, delta, 0)
    down = np.where(delta < 0, -delta, 0)

    roll_up = np.convolve(up, np.ones(period), 'full')[:len(up)] / period
    roll_down = np.convolve(down, np.ones(period), 'full')[:len(down)] / period

    rs = roll_up / (roll_down + 1e-10)
    rsi_vals = 100 - (100 / (1 + rs))

    return pl.Series(rsi_vals)

# =========================
# MACD
# =========================
def macd(df: pl.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9, col: str = "close"):
    fast_ema = ema(df, fast, col)
    slow_ema = ema(df, slow, col)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm_mean(span=signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

# =========================
# Bollinger Bands
# =========================
def bollinger_bands(df: pl.DataFrame, period: int = 20, col: str = "close", num_std: int = 2):
    sma_val = sma(df, period, col)
    rolling_std = df.select(pl.col(col).rolling_std(period)).to_series()
    upper = sma_val + (rolling_std * num_std)
    lower = sma_val - (rolling_std * num_std)
    return sma_val, upper, lower

# =========================
# VWAP
# =========================
def vwap(df: pl.DataFrame):
    pv = (df["close"] * df["volume"]).cumsum()
    vol = df["volume"].cumsum()
    return pv / (vol + 1e-10)

# =========================
# ADX (Average Directional Index)
# =========================
def adx(df: pl.DataFrame, period: int = 14):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()

    tr = np.maximum(high[1:] - low[1:], 
                    np.abs(high[1:] - close[:-1]), 
                    np.abs(low[1:] - close[:-1]))
    atr = np.convolve(tr, np.ones(period), 'valid') / period

    plus_dm = np.where((high[1:] - high[:-1]) > (low[:-1] - low[1:]), 
                       np.maximum(high[1:] - high[:-1], 0), 0)
    minus_dm = np.where((low[:-1] - low[1:]) > (high[1:] - high[:-1]), 
                        np.maximum(low[:-1] - low[1:], 0), 0)

    plus_di = 100 * (np.convolve(plus_dm, np.ones(period), 'valid') / atr)
    minus_di = 100 * (np.convolve(minus_dm, np.ones(period), 'valid') / atr)

    dx = (np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)) * 100
    adx_vals = np.convolve(dx, np.ones(period), 'valid') / period
    return pl.Series(np.concatenate([[np.nan] * (len(close) - len(adx_vals)), adx_vals]))

# =========================
# EMV (Ease of Movement)
# =========================
def emv(df: pl.DataFrame, period: int = 14):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    vol = df["volume"].to_numpy()
    mid = (high + low) / 2
    box_ratio = vol / (high - low + 1e-10)
    emv_vals = (mid[1:] - mid[:-1]) / box_ratio[1:]
    emv_smooth = np.convolve(emv_vals, np.ones(period), 'valid') / period
    return pl.Series(np.concatenate([[np.nan] * (len(high) - len(emv_smooth) - 1), emv_smooth]))


# ind_extra.py
import polars as pl
import numpy as np

# =========================
# ATR (Average True Range)
# =========================
def atr(df: pl.DataFrame, period: int = 14) -> pl.Series:
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()

    tr = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1])
    ])
    atr_vals = np.convolve(tr, np.ones(period), "valid") / period
    return pl.Series(
        np.concatenate([[np.nan] * (len(close) - len(atr_vals)), atr_vals])
    )

# =========================
# Supertrend
# =========================
def supertrend(df: pl.DataFrame, period: int = 10, multiplier: float = 3.0) -> pl.Series:
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()

    # ATR for bands
    tr = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1])
    ])
    atr_vals = np.convolve(tr, np.ones(period), "valid") / period
    atr_vals = np.concatenate([[np.nan] * (len(close) - len(atr_vals)), atr_vals])

    hl2 = (high + low) / 2
    upperband = hl2 - (multiplier * atr_vals)
    lowerband = hl2 + (multiplier * atr_vals)

    supertrend = np.zeros(len(close))
    direction = True  # True = uptrend, False = downtrend

    for i in range(1, len(close)):
        if close[i] > lowerband[i - 1]:
            direction = True
        elif close[i] < upperband[i - 1]:
            direction = False

        supertrend[i] = lowerband[i] if direction else upperband[i]

    return pl.Series(supertrend)

