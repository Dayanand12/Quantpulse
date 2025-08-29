# run_client.py

from Data_ingestion.config_loader import load_config, load_stocks
from Data_ingestion.client import ZerodhaClient
from Data_ingestion.data_manager import DataManager
import os
import pandas as pd
import time


def init_client(config_file="config.yaml"):
    """Initialize Zerodha client from config."""
    config = load_config(config_file)
    exchange = config["settings"]["exchange"]
    print(exchange)
    client = ZerodhaClient(
        exchange,
        api_key=config["zerodha"]["api_key"],
        api_secret=config["zerodha"]["api_secret"],
        access_token=None  # auto-generate if missing
    )
    return client, config
        

def fetch_historical(config_file="config.yaml", stocks_file="stocks.json", output_dir="historical_data"):
    """Fetch historical data and save to CSV."""
    config = load_config(config_file)
    stocks = load_stocks(stocks_file)

    client = init_client(config_file)[0]
    data_manager = DataManager(client, config)

    print("📥 Fetching historical data...")
    hist = data_manager.fetch_all_historical(stocks)

    os.makedirs(output_dir, exist_ok=True)

    for symbol, data in hist.items():
        if data:  # only if not empty
            df = pd.DataFrame(data)
            file_path = f"{output_dir}/{symbol}_historical.csv"
            df.to_csv(file_path, index=False)
            print(f"✅ Saved {symbol} data to {file_path}")

    return hist


def start_live(config_file="config.yaml", stocks_file="stocks.json"):
    """Start live WebSocket streaming."""
    config = load_config(config_file)
    stocks = load_stocks(stocks_file)
    exchange = config["settings"]["exchange"]

    client, _ = init_client(config_file)
    data_manager = DataManager(client, config)

    print("📡 Starting live data stream...")
    client.start_live_data(stocks, exchange)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("⏹ Exiting...")
        client.kws.close()

    return client
