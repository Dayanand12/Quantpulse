# data_handler.py
import pandas as pd

# Initialize the DataFrame with correct column names, including 'timestamp'
data = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

# Function to append tick data
def append_tick(tick):
    global data

    # Ensure the tick dictionary matches the order of columns in the data DataFrame
    new_row = {
        'timestamp': tick['timestamp'],
        'open': tick['open'],
        'high': tick['high'],
        'low': tick['low'],
        'close': tick['close'],
        'volume': tick['volume']
    }

    # Append the new row to the data DataFrame using pd.concat
    new_row_df = pd.DataFrame([new_row])
    data = pd.concat([data, new_row_df], ignore_index=True)

# Function to get the current data
def get_data():
    return data

# Function to reset the data (useful for backtesting or resetting for new sessions)
def reset_data():
    global data
    data = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    print("Data reset to initial state.")