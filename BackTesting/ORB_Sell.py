# ORB_Sell_Polars.py
import polars as pl
from dataclasses import dataclass
from ind.trend_ind import IndicatorCalculator

@dataclass
class StrategyConfig:
    rsi_period: int = 14
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_sell: float = 45.0
    orb_minutes: int = 5           # Opening range minutes
    adx_filter: float = 20.0       # ADX > 20
    sl_atr: float = 1.5
    tp_atr: float = 2.0
    trailing_perc: float = 0.3     # 30% trailing stop


def run_strategy(df: pl.DataFrame, symbol: str, config: StrategyConfig):
    # Ensure date column is datetime without timezone
    pdf = df.with_columns([pl.col("date").dt.replace_time_zone(None)])
    pdf = pdf.sort("date")  # sort by datetime
    pdf = pdf.with_columns(pl.col("date").dt.date().alias("date_only"))

    # Indicators (scalar for the symbol)
    rsi_val = IndicatorCalculator.rsi(symbol, pdf, config.rsi_period)[symbol]
    ema_fast_val = IndicatorCalculator.ema(symbol, pdf, config.ema_fast)[symbol]
    ema_slow_val = IndicatorCalculator.ema(symbol, pdf, config.ema_slow)[symbol]
    adx_val = IndicatorCalculator.adx(symbol, pdf, 14)[symbol]
    atr_val = IndicatorCalculator.atr(symbol, pdf, 14)[symbol]

    # Trade state
    position = None
    entry_price = None
    stop_loss = None
    target = None
    highest_profit_price = None
    trades_today = {"SELL": 0}

    signals, entries, stops, targets, trails = [], [], [], [], []

    current_day = None
    orb_high = None

    for i in range(len(pdf)):
        row = pdf[i]
        signal = None
        trailing_stop = None

        # Convert Polars date Series to Python date
        row_day = row["date_only"].item() if hasattr(row["date_only"], "item") else row["date_only"]

        if row_day != current_day:
            current_day = row_day
            trades_today = {"SELL": 0}
            day_data = pdf.filter(pl.col("date_only") == current_day)
            orb_high = day_data.head(config.orb_minutes)["high"].max()

        # EXIT logic for SELL
        if position == "SELL":
            close_val = row["close"].item()
            high_val = row["high"].item()
            low_val = row["low"].item()

            if highest_profit_price is not None and close_val < highest_profit_price:
                highest_profit_price = close_val
                trail_distance = (entry_price - highest_profit_price) * config.trailing_perc
                new_stop = highest_profit_price + trail_distance
                if stop_loss is not None and new_stop < stop_loss:
                    stop_loss = new_stop
                    signal = "Trailing Stop adjusted"

            if stop_loss is not None and high_val >= stop_loss:
                signal = "StopLoss Hit"
                position = None
            elif target is not None and low_val <= target:
                signal = "Target Hit"
                position = None

        # ENTRY logic for SELL
        if position is None and trades_today["SELL"] < 1:
            close_val = row["close"].item()
            if (
                close_val < ema_fast_val < ema_slow_val and
                rsi_val < config.rsi_sell and
                close_val < orb_high and
                adx_val > config.adx_filter
            ):
                signal = "SELL"
                position = "SELL"
                entry_price = close_val
                stop_loss = entry_price + config.sl_atr * atr_val
                target = entry_price - config.tp_atr * atr_val
                highest_profit_price = entry_price
                trades_today["SELL"] += 1

        trailing_stop = stop_loss if position is not None else None

        signals.append(signal)
        entries.append(entry_price)
        stops.append(stop_loss)
        targets.append(target)
        trails.append(trailing_stop)

    pdf = pdf.with_columns([
        pl.Series("Signal", signals),
        pl.Series("EntryPrice", entries),
        pl.Series("StopLoss", stops),
        pl.Series("Target", targets),
        pl.Series("TrailingSL", trails)
    ])

    return pdf.select(["date", "Signal", "EntryPrice", "StopLoss", "Target", "TrailingSL"])\
              .filter(pl.col("Signal").is_not_null())
