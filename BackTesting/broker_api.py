# Mocked broker API for backtesting
def place_order(symbol, qty, order_type):
    print(f"Mock Order: {order_type} {qty} of {symbol} placed.")

def get_live_ticks(symbol, callback):
    # For backtest mode, this function is unnecessary, but you could add mock data here if needed
    pass