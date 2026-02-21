STRATEGY_CONFIG = {
    "name": "ORB_Strategy",
    "symbol": "ETERNAL",
    "timeframe": "5minute",
    "entry_type": ["SELL"],  # "BUY" or "SELL"
    "conditions": [
        {"lhs": "Close", "op": "<", "rhs": "EMA(close,9)"},
        {"lhs": "EMA(close,9)", "op": "<", "rhs": "EMA(close,21)"},
        {"lhs": "RSI_MA(14,20)", "op": "<", "rhs": "45"},
        {"lhs": "Close", "op": "<", "rhs": "ORB(High,15)"},
        {"lhs": "ADX(14)", "op": ">", "rhs": "27"}
    ],
    "stoploss_pct": 0.8,        # 0.8%
    "trailing_pct": 0.1,        # 0.3%
    "target_pct": 2.0,          # 2%
    "quantity": 50,
    "max_capital": 100000,
    "max_cycles_per_day": 10
}
