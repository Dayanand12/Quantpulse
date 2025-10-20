# main.py
import polars as pl
#from BackTesting.stratergy2 import run_strategy, StrategyConfig
from BackTesting.ORB_Sell import run_strategy, StrategyConfig
from Data_ingestion.run_client import initialize_trading_environment
from data.fut_data.fetch_data import fetch_data

symbol = "ULTRACEMCO"
config = StrategyConfig()


client, _, stocks, data_manager = initialize_trading_environment(
        config_file="Data_ingestion/config.yaml",
        json_file="Data_ingestion/stocks.json"  # <-- You can pass any JSON file here
    )


df = fetch_data(
    client,
    symbol=symbol,
    interval="30minute",
    output_dir="fut_data"
)
# Example: Load data from CSV (replace with your live data source)
#df = pl.read_csv(r"fut_data\ULTRACEMCO_2025-10-28_5minute.csv")  # must contain ['date','open','high','low','close','volume']

# Convert Polars DataFrame to Pandas for run_strategy
#df_pandas = df.to_pandas()


# Run strategy
signals_df = run_strategy(df, symbol, config)

# Save or display signals
signals_df.write_csv(f"{symbol}_signals_output.csv")


print(signals_df.head())
