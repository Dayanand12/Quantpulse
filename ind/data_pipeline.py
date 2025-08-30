import polars as pl
from datetime import datetime
from ind.trend_ind import rsi, ema, macd

class SymbolData:
    def __init__(self, symbol, hist_df=None):
        """
        symbol: string symbol name
        hist_df: polars DataFrame with historical OHLCV + time columns
        """
        self.symbol = symbol
        # Use provided historical DF or initialize empty OHLCV DataFrame
        if hist_df is None:
            self.df = pl.DataFrame({
                "open": [],
                "high": [],
                "low": [],
                "close": [],
                "volume": [],
                "time": []
            })
        else:
            self.df = hist_df

        self.indicators = {}  # cache for computed indicators

    def append_live_tick(self, last_tick):
        """
        Append a new live tick to self.df.
        last_tick: dict containing at least 'close' and optionally 'time', 'open', 'high', 'low', 'volume'
                   OR a float (interpreted as 'close')
        """
        # Convert float to dict
        if isinstance(last_tick, (int, float)):
            last_tick = {"close": last_tick}

        # Build a new row dynamically based on self.df columns
        new_row_dict = {}
        for col in self.df.columns:
            if col in last_tick:
                new_row_dict[col] = last_tick[col]
            elif col == "time":
                new_row_dict[col] = datetime.now()
            else:
                new_row_dict[col] = None

        # Append the new row safely
        self.df = self.df.vstack(pl.DataFrame([new_row_dict]))

    def get_indicator(self, name, **params):
        """Compute and cache indicator"""
        name_lower = name.lower()

        if name_lower == "rsi":
            period = params.get("period", 14)
            self.indicators[f"RSI_{period}"] = rsi(self.df, period)
            return self.indicators[f"RSI_{period}"]

        if name_lower == "ema":
            period = params.get("period", 14)
            self.indicators[f"EMA_{period}"] = ema(self.df, period)
            return self.indicators[f"EMA_{period}"]

        if name_lower == "macd":
            fast = params.get("fast", 12)
            slow = params.get("slow", 26)
            signal = params.get("signal", 9)
            macd_line, signal_line, hist = macd(self.df, fast, slow, signal)
            self.indicators[f"MACD_{fast}_{slow}_{signal}"] = (macd_line, signal_line, hist)
            return self.indicators[f"MACD_{fast}_{slow}_{signal}"]
