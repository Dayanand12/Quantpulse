# strategy_acd.py
import polars as pl
from dataclasses import dataclass


@dataclass
class StrategyConfig:
    opening_range_minutes: int = 15   # ORB window
    offset: float = 0.0015            # % offset for A-up / A-down
    sl_mult: float = 1.5              # Stop loss multiple of OR range
    tp_mult: float = 2.0              # Take profit multiple of OR range
    max_trades: int = 1               # Max trades per side per day


def run_strategy(df, symbol: str, config: StrategyConfig):
    """
    ACD Strategy (Mark Fisher's Opening Range Breakout).
    Entry: Break of A-up/A-down levels from the opening range.
    Exit: SL/TP based on OR size.
    """

    # If input is Polars -> convert to Pandas
    if isinstance(df, pl.DataFrame):
        pdf = df.to_pandas()
    else:
        pdf = df  # already pandas

    # Calculate Opening Range (first N minutes)
    opening_range = pdf.iloc[:config.opening_range_minutes]
    OR_high = opening_range["high"].max()
    OR_low = opening_range["low"].min()
    OR_range = OR_high - OR_low

    # Define A levels
    A_up = OR_high * (1 + config.offset)
    A_down = OR_low * (1 - config.offset)

    # Trade state
    position = None
    entry_price = None
    stop_loss = None
    target = None
    trades_today = {"BUY": 0, "SELL": 0}

    signals = []

    for i in range(len(pdf)):
        row = pdf.iloc[i]
        signal = None

        # ENTRY conditions
        if position is None:
            if row["close"] > A_up and trades_today["BUY"] < config.max_trades:
                signal = "BUY"
                position = "BUY"
                entry_price = row["close"]
                stop_loss = entry_price - config.sl_mult * OR_range
                target = entry_price + config.tp_mult * OR_range
                trades_today["BUY"] += 1

            elif row["close"] < A_down and trades_today["SELL"] < config.max_trades:
                signal = "SELL"
                position = "SELL"
                entry_price = row["close"]
                stop_loss = entry_price + config.sl_mult * OR_range
                target = entry_price - config.tp_mult * OR_range
                trades_today["SELL"] += 1

        # EXIT conditions
        elif position == "BUY":
            if row["low"] <= stop_loss or row["high"] >= target:
                signal = "EXIT_BUY"
                position = None

        elif position == "SELL":
            if row["high"] >= stop_loss or row["low"] <= target:
                signal = "EXIT_SELL"
                position = None

        # If no signal, log it
        if signal is None:
            print(f"[{row['date']}] No signal (waiting)")

        signals.append(signal)

    pdf["Signal"] = signals
    pdf = pdf[["date", "Signal"]].dropna()

    return pdf

