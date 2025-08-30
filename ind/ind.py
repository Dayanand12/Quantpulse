import pandas as pd
import numpy as np
import talib

def get_symbol_history(hist_dict, symbol, period, current_price=None):
    """
    Fetch historical + live data for a given symbol, 
    with enough warmup buffer for indicators.
    """
    # ensure hist data is a DataFrame
    data = hist_dict.get(symbol)

    if isinstance(data, list):
        df = pd.DataFrame(data)
    else:
        df = data.copy()

    # keep only required cols
    df = df[["date", "open", "high", "low", "close", "volume"]]

    # add latest LTP
    if current_price:
        new_row = {
            "date": pd.Timestamp.now(),
            "open": current_price,
            "high": current_price,
            "low": current_price,
            "close": current_price,
            "volume": 0,
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    # extra buffer for warmup (for rolling indicators)
    df = df.tail(period * 5).reset_index(drop=True)

    return df









    


