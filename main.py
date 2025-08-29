from Data_ingestion.run_client import fetch_historical, start_live
import time

if __name__ == "__main__":

    # -------------------------
    # Historical data example
    # -------------------------
    # hist = fetch_historical("Data_ingestion/config.yaml", "Data_ingestion/stocks.json")
    # print(hist)

    # -------------------------
    # Live data example
    # -------------------------
    client = start_live("Data_ingestion/config.yaml", "Data_ingestion/stocks.json")

    try:
        while True:
            # Access latest data in a variable
            latest_data = client.market_data
            print(latest_data.get("INFY"))

            time.sleep(1)

    except KeyboardInterrupt:
        print("⏹ Exiting...")
        client.kws.close()


