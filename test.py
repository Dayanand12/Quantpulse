from Data_ingestion.run_client import fetch_historical, start_live
from ind.data_pipeline import SymbolData


import polars as pl
import time
import sys
import os

root = os.path.dirname(os.path.abspath(__file__))
config_file = os.path.join(root, "Data_ingestion/config.yaml")
stocks_file = os.path.join(root, "Data_ingestion/stocks.json")

# 1️⃣ Fetch historical data
hist_data = fetch_historical(config_file, stocks_file)  # returns dict {symbol: DataFrame}
symbols = {sym: SymbolData(sym, pl.DataFrame(df)) for sym, df in hist_data.items()}

# 2️⃣ Start live
client = start_live(config_file, stocks_file)  # will run WebSocket in background

# 3️⃣ Feed live ticks dynamically to SymbolData
try:
    while True:
        for sym, data in symbols.items():
            if sym in client.market_data:
                last_price = client.market_data[sym]["LTP"]
                data.append_live_tick(last_price)

                # Example: calculate RSI(9) on historical + live data
                rsi_series = data.get_indicator("rsi", period=9)
                print(f"{sym} RSI(9): {rsi_series[-1]}")

        time.sleep(1)
except KeyboardInterrupt:
    print("Exiting...")
    client.kws.close()
