from Data_ingestion.run_client import fetch_historical, start_live
from ind.trend_ind import macd
import time
import polars as pl
from typing import List, Dict, Any
from ta.momentum import RSIIndicator
import pandas as pd


def fetch_to_df(hist: List[Dict[str, Any]]) -> pl.DataFrame:
    """
    Converts a list of OHLCV dicts into a Polars DataFrame with proper types.
    
    hist: List of dictionaries with keys:
        'date', 'open', 'high', 'low', 'close', 'volume'
    
    Returns:
        Polars DataFrame with:
            - date as pl.Datetime
            - open, high, low, close as Float64
            - volume as Int64
    """
    float_cols = ["open", "high", "low", "close"]
    int_cols = ["volume"]
    clean_hist = []

    for row in hist:
        if not isinstance(row, dict):
            continue  # skip invalid rows
        # Convert numeric types
        for col in float_cols:
            row[col] = float(row[col])
        for col in int_cols:
            row[col] = int(row[col])
        clean_hist.append(row)

    # Create DataFrame
    df = pl.DataFrame(clean_hist)

    # Cast date column safely
    if "date" in df.columns:
        df = df.with_columns([
            pl.col("date").cast(pl.Datetime)
        ])
    
    return df


def get_rsi_last(hist: pd.DataFrame, current_price: float, period: int = 9):
    """
    Returns RSI using last `period` historical bars + current LTP
    """
    last_n = hist['close'].tail(period).tolist()
    last_n.append(current_price)
    close_series = pd.Series(last_n)
    rsi = RSIIndicator(close_series, window=period).rsi().iloc[-1]
    return rsi

# --------------------
# Example usage
# hist = fetched OHLCV data as list of dicts

if __name__ == "__main__":

    # -------------------------
    # Historical data example
    # -------------------------
    hist = fetch_historical("Data_ingestion/config.yaml", "Data_ingestion/stocks.json")
    df = fetch_to_df(hist)
    

        # -------------------------
        # Live data example
        # -------------------------
    client = start_live("Data_ingestion/config.yaml", "Data_ingestion/stocks.json")

    try:
        while True:
            # Access latest data in a variable
            latest_data = client.market_data
            #print(latest_data.get("HSCL"))
            ltp = latest_data.get("HSCL", {}).get("LTP")
            rsi_9 = get_rsi_last(df, ltp, period=9)
            print("Current RSI (9-period):", rsi_9)
          


            time.sleep(1)
            

    except KeyboardInterrupt:
        print("⏹ Exiting...")
        client.kws.close()


