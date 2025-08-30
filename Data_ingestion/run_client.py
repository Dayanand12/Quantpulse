# run_client.py

from Data_ingestion.config_loader import load_config, load_stocks
from Data_ingestion.client import ZerodhaClient
from Data_ingestion.data_manager import DataManager
import os
import pandas as pd
import time

# -------------------------
# Initialize client
# -------------------------
def init_client(config_file="config.yaml"):
    config = load_config(config_file)
    exchange = config["settings"]["exchange"]
    client = ZerodhaClient(
        exchange,
        api_key=config["zerodha"]["api_key"],
        api_secret=config["zerodha"]["api_secret"],
        access_token=None  # auto-generate if missing
    )
    return client, config


# -------------------------
# Fetch Historical Data
# -------------------------
def fetch_historical(config_file="config.yaml", stocks_file="stocks.json", output_dir="historical_data"):
    config = load_config(config_file)
    stocks = load_stocks(stocks_file)

    client = init_client(config_file)[0]
    data_manager = DataManager(client, config)

    print("📥 Fetching historical data...")
    hist = data_manager.fetch_all_historical(stocks)

    os.makedirs(output_dir, exist_ok=True)
    for symbol, data in hist.items():
        if data:
            df = pd.DataFrame(data)
            file_path = f"{output_dir}/{symbol}_historical.csv"
            df.to_csv(file_path, index=False)
            print(f"✅ Saved {symbol} data to {file_path}")

    return hist

def fetch_historical_ind(config_file="config.yaml", stocks_file="stocks.json", output_dir="historical_data"):
    config = load_config(config_file)
    stocks = load_stocks(stocks_file)

    client = init_client(config_file)[0]
    data_manager = DataManager(client, config)

    print("📥 Fetching historical data...")
    hist = data_manager.fetch_historical_ind(stocks)

    os.makedirs(output_dir, exist_ok=True)
    for symbol, data in hist.items():
        if data:
            df = pd.DataFrame(data)
            file_path = f"{output_dir}/{symbol}_historical.csv"
            df.to_csv(file_path, index=False)
            print(f"✅ Saved {symbol} data to {file_path}")

    return hist

# -------------------------
# Start Live Data
# -------------------------
def start_live(config_file="config.yaml", stocks_file="stocks.json"):
    config = load_config(config_file)
    stocks = load_stocks(stocks_file)
    exchange = config["settings"]["exchange"]

    client, _ = init_client(config_file)
    data_manager = DataManager(client, config)

    # Ensure market_data dict exists immediately
    client.market_data = {}

    print("📡 Starting live data stream...")
    client.start_live_data(stocks, exchange)

    # Return the client so main can access market_data
    return client
