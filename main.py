from Data_ingestion.run_client import fetch_historical, start_live, fetch_historical_ind
import time
import polars as pl
from typing import List, Dict, Any
import talib
from Data_ingestion.config_loader import load_stocks
import pandas as pd

from ind.ind import get_symbol_history








# -------------------- MAIN --------------------
if __name__ == "__main__":
    # Fetch historical data
    #hist = fetch_historical("Data_ingestion/config.yaml", "Data_ingestion/stocks.json")
    hist = fetch_historical_ind("Data_ingestion/config.yaml", "Data_ingestion/stocks.json")
    symbols=load_stocks("Data_ingestion/stocks.json")
    
    

    #print("✅ Historical DataFrame ready:", df.columns)

    # Start live client
    client = start_live("Data_ingestion/config.yaml", "Data_ingestion/stocks.json")

    try:
        while True:
            latest_data = client.market_data
            #ltp = latest_data.get(symbols, {}).get("LTP")
            ltp_map = {symbol: latest_data.get(symbol, {}).get("LTP") for symbol in symbols}
            

      
            RSI = {}   # create once before loop

            for symbol, ltp in ltp_map.items():   # ltp_map = {"HSCL": 445.9, "INFY": 1469.6}
                if ltp is not None:
                    df = get_symbol_history(hist, symbol, period=14, current_price=ltp)
                    rsi = talib.RSI(df["close"], timeperiod=14)
                    rsi = rsi.dropna()  # drop NaN
                    if len(rsi) > 1:    # ensure enough values
                        RSI[symbol] = rsi.iloc[-2]

            print("RSI:", RSI)



            time.sleep(1)

    except KeyboardInterrupt:
            print("⏹ Exiting...")
            client.kws.close()

