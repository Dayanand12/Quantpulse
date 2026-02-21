# backend_strategy_engine.py
import polars as pl
import numpy as np
import talib
from Data_ingestion.run_client import initialize_trading_environment
from data.fut_data.fetch_data import fetch_data

# --- Indicator Wrappers (series version) ---
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
        rsi_ma = talib.SMA(rsi_series, timeperiod=ma_period)
        return pl.Series(f"RSI_MA_{rsi_period}_{ma_period}", rsi_ma)

    @staticmethod
    def adx(df: pl.DataFrame, period=14):
        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        close = df["close"].to_numpy()
        return pl.Series(f"ADX_{period}", talib.ADX(high, low, close, timeperiod=period))

    @staticmethod
    def atr(df: pl.DataFrame, period=14):
        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        close = df["close"].to_numpy()
        return pl.Series(f"ATR_{period}", talib.ATR(high, low, close, timeperiod=period))

    @staticmethod
    def opening_range_high(df: pl.DataFrame, minutes=5):
        # assume df is already sorted by date, time; take first N rows per day
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


# --- Condition Evaluator ---
class ConditionEvaluator:
    OPS = {
        "<": np.less,
        "<=": np.less_equal,
        ">": np.greater,
        ">=": np.greater,
        "==": np.equal,
        "!=": np.not_equal
    }

    def __init__(self, df: pl.DataFrame):
        self.df = df

    def parse_operand(self, expr: str):
        expr = expr.strip()
        if expr.replace(".", "", 1).isdigit():
            # numeric constant
            return float(expr)
        # Check for indicators
        if expr.startswith("EMA"):
            col = expr.split("(")[1].split(")")[0].split(",")[0]
            period = int(expr.split("(")[1].split(")")[0].split(",")[1])
            return self.df[f"EMA_{period}"]
        if expr.startswith("RSI_MA"):
            args = expr.split("(")[1].split(")")[0].split(",")
            rsi_period, ma_period = int(args[0]), int(args[1])
            return self.df[f"RSI_MA_{rsi_period}_{ma_period}"]
        if expr.startswith("RSI"):
            period = int(expr.split("(")[1].split(")")[0])
            return self.df[f"RSI_{period}"]
        if expr.startswith("ADX"):
            period = int(expr.split("(")[1].split(")")[0])
            return self.df[f"ADX_{period}"]
        if expr.startswith("ORB"):
            return self.df["ORB_High"]
        if expr == "Close":
            return self.df["close"]
        if expr == "High":
            return self.df["high"]
        if expr == "Low":
            return self.df["low"]
        raise ValueError(f"Unknown operand: {expr}")

    def evaluate(self, condition_list):
        masks = []
        for cond in condition_list:
            lhs = self.parse_operand(cond["lhs"])
            rhs = self.parse_operand(cond["rhs"])
            op_func = self.OPS[cond["op"]]
            mask = op_func(lhs.to_numpy(), rhs.to_numpy() if isinstance(rhs, pl.Series) else rhs)
            masks.append(mask)
        final_mask = np.logical_and.reduce(masks)
        return final_mask


# --- Trade Engine ---
class TradeEngine:
    def __init__(self, df: pl.DataFrame):
        self.df = df

    def generate_signals(self, buy_mask, sell_mask):
        signals = []
        for b, s in zip(buy_mask, sell_mask):
            if b:
                signals.append("BUY")
            elif s:
                signals.append("SELL")
            else:
                signals.append(None)
        self.df = self.df.with_columns(pl.Series("Signal", signals))
        return self.df


# --- Full Backend Engine ---
class StrategyEngine:
    def __init__(self, df: pl.DataFrame, strategy_config: dict):
        self.df = df
        self.config = strategy_config

    def compute_indicators(self):
        """
        Compute all indicators required by the strategy conditions.
        Handles EMA, RSI, RSI_MA, ADX, ORB.
        """
        for cond in self.config["conditions"]:
            for key in ["lhs", "rhs"]:
                expr = cond[key].strip()

                # --- Skip numeric constants ---
                if expr.replace(".", "", 1).isdigit():
                    continue

                # --- EMA ---
                if expr.startswith("EMA"):
                    # Example: EMA(close,9)
                    parts = expr.split("(")[1].split(")")[0].split(",")
                    col = parts[0].strip()
                    period = int(parts[1].strip())
                    col_name = f"EMA_{period}"
                    if col_name not in self.df.columns:
                        self.df = self.df.with_columns(
                            IndicatorCalculator.ema(self.df, col=col, period=period)
                        )

                # --- RSI_MA ---
                elif expr.startswith("RSI_MA"):
                    # Example: RSI_MA(14,20)
                    args = expr.split("(")[1].split(")")[0].split(",")
                    rsi_period, ma_period = int(args[0].strip()), int(args[1].strip())
                    col_name = f"RSI_MA_{rsi_period}_{ma_period}"
                    if col_name not in self.df.columns:
                        self.df = self.df.with_columns(
                            IndicatorCalculator.rsi_ma(self.df, rsi_period=rsi_period, ma_period=ma_period)
                        )

                # --- RSI ---
                elif expr.startswith("RSI"):
                    # Example: RSI(14)
                    period = int(expr.split("(")[1].split(")")[0].strip())
                    col_name = f"RSI_{period}"
                    if col_name not in self.df.columns:
                        self.df = self.df.with_columns(
                            IndicatorCalculator.rsi(self.df, period=period)
                        )

                # --- ADX ---
                elif expr.startswith("ADX"):
                    # Example: ADX(14)
                    period = int(expr.split("(")[1].split(")")[0].strip())
                    col_name = f"ADX_{period}"
                    if col_name not in self.df.columns:
                        self.df = self.df.with_columns(
                            IndicatorCalculator.adx(self.df, period=period)
                        )

                # --- ORB (Opening Range High) ---
                elif expr.startswith("ORB"):
                    # Example: ORB(High,5) or ORB(High) default 5
                    if "ORB_High" not in self.df.columns:
                        try:
                            minutes = int(expr.split("(")[1].split(")")[0].split(",")[1].strip())
                        except IndexError:
                            minutes = 5  # default
                        self.df = self.df.with_columns(
                            IndicatorCalculator.opening_range_high(self.df, minutes=minutes)
                        )

                # --- Close / High / Low --- (no calculation needed)
                elif expr in ["Close", "High", "Low"]:
                    continue

                else:
                    raise ValueError(f"Unknown indicator or operand: {expr}")

        return self.df


    def run_strategy(self):
        # Compute all required indicators
        self.df = self.compute_indicators()
        evaluator = ConditionEvaluator(self.df)
        buy_mask = evaluator.evaluate(self.config["conditions"]) if "BUY" in self.config.get("entry_type", []) else np.zeros(len(self.df), dtype=bool)
        sell_mask = evaluator.evaluate(self.config["conditions"]) if "SELL" in self.config.get("entry_type", []) else np.zeros(len(self.df), dtype=bool)
        engine = TradeEngine(self.df)
        self.df = engine.generate_signals(buy_mask, sell_mask)
        return self.df
    


import polars as pl

# Your 5-min dataframe
#df = pl.read_csv("your_5min_data.csv")
symbol = "ULTRACEMCO"



client, _, stocks, data_manager = initialize_trading_environment(
        config_file="Data_ingestion/config.yaml",
        json_file="Data_ingestion/stocks.json"  # <-- You can pass any JSON file here
    )


df = fetch_data(
    client,
    symbol=symbol,
    interval="5minute",
    output_dir="fut_data")

# Convert datetime with timezone to naive datetime
df = df.with_columns(
    pl.col("date").dt.replace_time_zone(None)
)




strategy_config = {
    "name": "ORB_Strategy",
    "timeframe": "5min",
    "entry_type": ["SELL"],#"BUY"
    "conditions": [
        {"lhs": "Close", "op": "<", "rhs": "EMA(close,9)"},
        {"lhs": "EMA(close,9)", "op": "<", "rhs": "EMA(close,21)"},
        {"lhs": "RSI_MA(14,20)", "op": "<", "rhs": "45"},
        {"lhs": "Close", "op": "<", "rhs": "ORB(High,5)"},
        {"lhs": "ADX(14)", "op": ">", "rhs": "20"}
    ]
}

engine = StrategyEngine(df, strategy_config)
result_df = engine.run_strategy()
result_df.write_csv(f"{symbol}_signals_output.csv")
print(result_df.select(["date","close","Signal"]))

