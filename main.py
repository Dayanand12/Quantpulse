from Data_ingestion.run_client import fetch_historical, start_live, fetch_historical_ind
import time
import polars as pl
from typing import List, Dict, Any
import talib
from Data_ingestion.config_loader import load_stocks
import pandas as pd
from ind.ind import get_symbol_history




# strategy.py
from stratergies.niftydayfut import run_strategy, StrategyConfig
from ind.trend_ind import IndicatorCalculator
# Config for strategy
config = StrategyConfig(
    ema_fast=20,
    ema_slow=50,
    rsi_period=14,
    rsi_buy=30,
    rsi_sell=70,
    orb_minutes=15
)







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
            for symbol, ltp in ltp_map.items():   # ltp_map = {"HSCL": 445.9, "INFY": 1469.6}
                if ltp is not None:
                    df = get_symbol_history(hist, symbol, period=14, current_price=ltp)
                    rsi  = IndicatorCalculator.rsi(symbol, df, 14)
                    ema  = IndicatorCalculator.ema(symbol, df, 20)
                    macd = IndicatorCalculator.macd(symbol, df)
                    adx  = IndicatorCalculator.adx(symbol, df, 14)
                    atr  = IndicatorCalculator.atr(symbol, df, 14)
                    vwap = IndicatorCalculator.vwap(symbol, df)
                    orb  = IndicatorCalculator.orb(symbol, df, N=15)
                    signals = run_strategy(df, symbol, config)
                    



            time.sleep(1)

    except KeyboardInterrupt:
            print("⏹ Exiting...")
            client.kws.close()

