# later connect to broker / data provider
import random

def get_live_data(stock):
    return {
        "open": random.randint(100, 300),
        "prev_high": random.randint(90, 120),
        "volume": random.randint(50000, 200000),
        "ltp": random.randint(100, 300),
        "vwap": random.randint(100, 300),
        "rsi": random.randint(10, 90),
        "atr": random.randint(2, 10),
        "day_high": random.randint(100, 300),
        "volume_ratio": random.random() * 3,
        "avg20": random.randint(50, 200),
        "macd": random.random() * 2,
        "signal": random.random() * 2,
    }