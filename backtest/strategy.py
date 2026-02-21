from .indicators import IndicatorCalculator
from .conditions import ConditionEvaluator
from .trade_engine import TradeEngine
import numpy as np


class StrategyEngine:
    def __init__(self, df, config):
        self.df = df
        self.config = config

    def compute_indicators(self):
        for cond in self.config["conditions"]:
            for key in ["lhs","rhs"]:
                expr = cond[key].strip()
                if expr.replace(".", "", 1).isdigit():
                    continue
                if expr.startswith("EMA"):
                    parts = expr.split("(")[1].split(")")[0].split(",")
                    col = parts[0].strip()
                    period = int(parts[1].strip())
                    if f"EMA_{period}" not in self.df.columns:
                        self.df = self.df.with_columns(IndicatorCalculator.ema(self.df, col=col, period=period))
                elif expr.startswith("RSI_MA"):
                    args = expr.split("(")[1].split(")")[0].split(",")
                    rsi_period, ma_period = int(args[0]), int(args[1])
                    if f"RSI_MA_{rsi_period}_{ma_period}" not in self.df.columns:
                        self.df = self.df.with_columns(IndicatorCalculator.rsi_ma(self.df, rsi_period=rsi_period, ma_period=ma_period))
                elif expr.startswith("RSI"):
                    period = int(expr.split("(")[1].split(")")[0])
                    if f"RSI_{period}" not in self.df.columns:
                        self.df = self.df.with_columns(IndicatorCalculator.rsi(self.df, period=period))
                elif expr.startswith("ADX"):
                    period = int(expr.split("(")[1].split(")")[0])
                    if f"ADX_{period}" not in self.df.columns:
                        self.df = self.df.with_columns(IndicatorCalculator.adx(self.df, period=period))

                elif expr.startswith("ORB"):
                    if "ORB_High" not in self.df.columns:
                        try:
                            minutes = int(expr.split("(")[1].split(")")[0].split(",")[1].strip())
                        except IndexError:
                            minutes = 5
                        self.df = self.df.with_columns(IndicatorCalculator.opening_range_high(self.df, minutes=minutes))
        return self.df

    def run_strategy(self):
        self.df = self.compute_indicators()
        evaluator = ConditionEvaluator(self.df)
        buy_mask = evaluator.evaluate(self.config["conditions"]) if "BUY" in self.config["entry_type"] else np.zeros(len(self.df), dtype=bool)
        sell_mask = evaluator.evaluate(self.config["conditions"]) if "SELL" in self.config["entry_type"] else np.zeros(len(self.df), dtype=bool)
        engine = TradeEngine(self.df, self.config)
        self.df = engine.generate_signals(buy_mask, sell_mask)
        return self.df

