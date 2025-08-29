# strategy_engine.py
import polars as pl
import talib
import dataclass

@dataclass
class StrategyConfig:
    def __init__(self,
                 ema_fast=20,
                 ema_slow=50,
                 rsi_period=14,
                 rsi_buy=30,
                 rsi_sell=70,
                 orb_minutes=15):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_buy = rsi_buy
        self.rsi_sell = rsi_sell
        self.orb_minutes = orb_minutes

def run_strategy(df: pl.DataFrame, config: StrategyConfig):
    """
    Run strategy on OHLCV DataFrame.
    Returns: Polars DataFrame with Buy/Sell signals only.
    """

    # Convert to pandas because talib works on numpy
    pdf = df.to_pandas()

    # Indicators
    pdf["EMA_FAST"] = talib.EMA(pdf["close"], timeperiod=config.ema_fast)
    pdf["EMA_SLOW"] = talib.EMA(pdf["close"], timeperiod=config.ema_slow)
    pdf["RSI"] = talib.RSI(pdf["close"], timeperiod=config.rsi_period)

    # Opening Range High/Low (first N mins)
    first_rows = pdf.iloc[:config.orb_minutes]
    orb_high, orb_low = first_rows["high"].max(), first_rows["low"].min()

    signals = []
    for i in range(len(pdf)):
        row = pdf.iloc[i]
        signal = None

        # BUY setup
        if (
            row["close"] > row["EMA_FAST"] > row["EMA_SLOW"]  # trend up
            and row["RSI"] > config.rsi_buy                  # momentum
            and row["close"] > orb_high                      # breakout
        ):
            signal = "BUY"

        # SELL setup
        elif (
            row["close"] < row["EMA_FAST"] < row["EMA_SLOW"]  # trend down
            and row["RSI"] < config.rsi_sell                  # momentum
            and row["close"] < orb_low                        # breakdown
        ):
            signal = "SELL"

        signals.append(signal)

    pdf["Signal"] = signals

    # Only keep timestamp + signal
    pdf = pdf[["datetime", "Signal"]].dropna()

    return pl.from_pandas(pdf)
