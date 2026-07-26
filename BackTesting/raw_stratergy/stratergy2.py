# strategy.py
import polars as pl
import talib
from dataclasses import dataclass
from ind.trend_ind import IndicatorCalculator


@dataclass
class StrategyConfig:
    rsi_period: int = 14
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_buy: float = 55.0
    rsi_sell: float = 45.0
    orb_minutes: int = 15
    adx_filter: float = 20.0
    atr_filter: float = 0.008 # minimum ATR % of price
    sl_atr: float = 1.5
    tp_atr: float = 2.0
    gap_filter: float = 0.01 # max gap allowed per day


def run_strategy(df: pl.DataFrame, symbol: str, config: StrategyConfig):
    """
    Intraday breakout strategy for Nifty Futures.
    Entry: EMA trend + RSI momentum + ORB breakout + ADX filter.
    Exit: ATR-based SL/TP or opposite signal.
    Filters: ATR threshold, gap filter, max 1 trade per side/day.
    """

    pdf = df.copy()

    # Indicators
    rsi  = IndicatorCalculator.rsi(symbol, pdf, config.rsi_period)
    ema_fast = IndicatorCalculator.ema(symbol, pdf, config.ema_fast)
    ema_slow = IndicatorCalculator.ema(symbol, pdf, config.ema_slow)
    adx  = IndicatorCalculator.adx(symbol, pdf, 14)
    atr  = IndicatorCalculator.atr(symbol, pdf, 14)   # float for live
    orb  = IndicatorCalculator.orb(symbol, pdf, N=config.orb_minutes)

    orb_high = orb[symbol]["high"]
    orb_low = orb[symbol]["low"]

    # Trade state trackers
    position = None
    entry_price = None
    stop_loss = None
    target = None
    trades_today = {"BUY": 0, "SELL": 0}

    signals = []

    for i in range(len(pdf)):
        row = pdf.iloc[i]
        signal = None

        # ATR & ADX filters
        if atr[symbol] / row["close"] < config.atr_filter:
            signal = None
            print(f"[{row['date']}] No signal (ATR filter)")
            signals.append(signal)
            continue
        if adx[symbol][i] < config.adx_filter:
            signal = None
            print(f"[{row['date']}] No signal (ADX filter)")
            signals.append(signal)
            continue

        # Gap filter (skip day if open gap > threshold)
        if i == 0:
            prev_close = row["close"]
            continue
        if abs((row["open"] - prev_close) / prev_close) > config.gap_filter:
            signal = None
            print(f"[{row['date']}] No signal (Gap filter)")
            signals.append(signal)
            continue

        # EXIT conditions if in trade
        if position is not None:
            if row["low"] <= stop_loss and position == "BUY":
                signal = "EXIT_BUY"
                position = None
            elif row["high"] >= stop_loss and position == "SELL":
                signal = "EXIT_SELL"
                position = None
            elif row["high"] >= target and position == "BUY":
                signal = "EXIT_BUY"
                position = None
            elif row["low"] <= target and position == "SELL":
                signal = "EXIT_SELL"
                position = None

        # ENTRY conditions if flat
        if position is None:
            if (
                row["close"] > ema_fast[symbol][i] > ema_slow[symbol][i]
                and rsi[symbol][i] > config.rsi_buy
                and row["close"] > orb_high[i]
                and trades_today["BUY"] < 1
            ):
                signal = "BUY"
                position = "BUY"
                entry_price = row["close"]
                stop_loss = entry_price - config.sl_atr * atr[symbol]
                target = entry_price + config.tp_atr * atr[symbol]
                trades_today["BUY"] += 1

            elif (
                row["close"] < ema_fast[symbol][i] < ema_slow[symbol][i]
                and rsi[symbol][i] < config.rsi_sell
                and row["close"] < orb_low[i]
                and trades_today["SELL"] < 1
            ):
                signal = "SELL"
                position = "SELL"
                entry_price = row["close"]
                stop_loss = entry_price + config.sl_atr * atr[symbol]
                target = entry_price - config.tp_atr * atr[symbol]
                trades_today["SELL"] += 1

        # If still no signal, log it
        if signal is None:
            print(f"[{row['date']}] No signal (waiting)")

        signals.append(signal)
        prev_close = row["close"]

    pdf["Signal"] = signals
    pdf = pdf[["date", "Signal"]].dropna()

    return pdf

