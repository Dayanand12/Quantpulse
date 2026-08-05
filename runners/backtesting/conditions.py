import numpy as np
import polars as pl

class ConditionEvaluator:
    OPS = {
        "<": np.less,
        "<=": np.less_equal,
        ">": np.greater,
        ">=": np.greater_equal,
        "==": np.equal,
        "!=": np.not_equal
    }

    def __init__(self, df: pl.DataFrame):
        self.df = df

    def parse_operand(self, expr: str):
        expr = expr.strip()
        if expr.replace(".", "", 1).isdigit():
            return float(expr)
        if expr.startswith("EMA"):
            parts = expr.split("(")[1].split(")")[0].split(",")
            col = parts[0].strip()
            period = int(parts[1].strip())
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
        return np.logical_and.reduce(masks)
