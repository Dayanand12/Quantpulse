from config_loader import load_config, load_stocks
from client import ZerodhaClient
from data_manager import DataManager
import os
import pandas as pd
import time




if __name__ == "__main__":
    # Load configs
    config = load_config("config.yaml")
    stocks = load_stocks("stocks.json")
    #stocks = load_stocks("comodity.json")
    exchange=config["settings"]["exchange"]
    # Init client
    client = ZerodhaClient(
        exchange,
        api_key=config["zerodha"]["api_key"],
        api_secret=config["zerodha"]["api_secret"],
        access_token=None  # auto-generate if missing
    )
    

    data_manager = DataManager(client, config)

    # client.start_live_data(["GOLD25OCTFUT"], exchange="MCX")

    # # Fetch historical data
    # hist = data_manager.fetch_all_historical(stocks)
    # #print("Sample Historical Data:", {k: v[:1] for k, v in hist.items()})

    # # Fetch live snapshots
    # live = data_manager.fetch_all_live_quotes(stocks)
    # #print("Live Quotes:", live)

    # Start WebSocket streaming
    client.start_live_data(stocks,exchange)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting...")
        client.kws.close()

    # # create folder if not exists
    # os.makedirs("historical_data", exist_ok=True)

    # # save each stock’s historical data into CSV
    # for symbol, data in hist.items():
    #     if data:  # only if data is not empty
    #         df = pd.DataFrame(data)
    #         file_path = f"historical_data/{symbol}_historical.csv"
    #         df.to_csv(file_path, index=False)
    #         print(f"✅ Saved {symbol} data to {file_path}")
