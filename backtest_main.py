import polars as pl
from Data_ingestion.run_client import initialize_trading_environment
from data.fut_data.fetch_data import fetch_data
from backtest.run_strategy import run_strategy_on_df
from backtest.config import STRATEGY_CONFIG
# Fetch your dataframe
symbol = STRATEGY_CONFIG["symbol"]
interval= STRATEGY_CONFIG["timeframe"]
client, _, stocks, data_manager = initialize_trading_environment(
        config_file="Data_ingestion/config.yaml",
        json_file="Data_ingestion/stocks.json"  # <-- You can pass any JSON file here
    )


df = fetch_data(
    client,
    symbol=symbol,
    interval=interval,
    output_dir="fut_data"
)

# Run strategy

result = run_strategy_on_df(df)

# Save signals to CSV
result.write_csv(f"{symbol}_strategy_signals.csv")

# Preview
print(result.select(["date", "close", "Signal", "EntryPrice", "ExitPrice", "StopLoss", "Target","ExitSignals"]))