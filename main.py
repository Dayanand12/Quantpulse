from Data_ingestion.run_client import fetch_historical, start_live


if __name__ == "__main__":

    # ✅ If you want Historical Data
    # hist = fetch_historical("config.yaml", "stocks.json")
    # print(hist)   # or process it

    # ✅ If you want Live Data
    start_live("Data_ingestion/config.yaml", "Data_ingestion/stocks.json")

    # ✅ If you want both
    # hist = fetch_historical("config.yaml", "stocks.json")
    # start_live("config.yaml", "stocks.json")
