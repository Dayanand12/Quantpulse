# backtest_runner.py
import pandas as pd
from BackTesting.raw_stratergy.strategy import on_tick
from data_handler import reset_data
from config import symbol

def run_backtest(csv_file):
    reset_data()
    data = pd.read_csv(csv_file)
    # Convert 'timestamp' column to datetime objects here
    if 'timestamp' in data.columns:  # Add a check for the column
        data['timestamp'] = pd.to_datetime(data['timestamp'])
    else:
        print("Error: 'timestamp' column not found in CSV file.")
        return

    for _, row in data.iterrows():
        tick = {
            'timestamp': row['timestamp'],
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': row['volume'],
            'oi': row['oi'] if 'oi' in row else None
        }
        on_tick(tick)

    print(f"Backtest Completed for {symbol}")