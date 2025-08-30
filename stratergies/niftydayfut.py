# strategy.py
import polars as pl
import talib
from dataclasses import dataclass
from ind.trend_ind import IndicatorCalculator


@dataclass
class StrategyConfig:
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_buy: int = 30
    rsi_sell: int = 70
    orb_minutes: int = 15


def run_strategy(df: pl.DataFrame, symbol: str, config: StrategyConfig):
    """
    Run strategy on OHLCV DataFrame using IndicatorCalculator.
    Returns: Polars DataFrame with Buy/Sell signals only.
    """

    # Convert Polars -> Pandas (for TA-Lib + IndicatorCalculator)
    pdf = df.copy()

    # Indicators
    rsi  = IndicatorCalculator.rsi(symbol, pdf, config.rsi_period)
    ema_fast = IndicatorCalculator.ema(symbol, pdf, config.ema_fast)
    ema_slow = IndicatorCalculator.ema(symbol, pdf, config.ema_slow)
    macd = IndicatorCalculator.macd(symbol, pdf)
    adx  = IndicatorCalculator.adx(symbol, pdf, 14)
    atr  = IndicatorCalculator.atr(symbol, pdf, 14)
    vwap = IndicatorCalculator.vwap(symbol, pdf)
    orb  = IndicatorCalculator.orb(symbol, pdf, N=config.orb_minutes)

    orb_high = orb[symbol]["high"]
    orb_low = orb[symbol]["low"]

    signals = []
    for i in range(len(pdf)):
        row = pdf.iloc[i]
        signal = None

        # BUY setup
        if (
            row["close"] > ema_fast[symbol] > ema_slow[symbol]  # trend up
            and rsi[symbol] > config.rsi_buy                   # momentum
            and row["close"] > orb_high                        # breakout
        ):
            signal = "BUY"

        # SELL setup
        elif (
            row["close"] < ema_fast[symbol] < ema_slow[symbol]  # trend down
            and rsi[symbol] < config.rsi_sell                  # momentum
            and row["close"] < orb_low                         # breakdown
        ):
            signal = "SELL"

        signals.append(signal)

    pdf["Signal"] = signals

    # Only keep timestamp + signal
    pdf = pdf[["date", "Signal"]].dropna()

    return pdf
