from kiteconnect import KiteConnect
import pandas as pd
import datetime as dt
import os
from Data_ingestion.config_loader import load_config, load_stocks
from Data_ingestion.client import initialize_trading_environment


# api_key = "1bfpnkeo1p80nft7"
# access_token = "RKdYwfIl0tUGjqOfOfsvZJjJCL7UzPwP"   # Generate via login flow
# kite = KiteConnect(api_key=api_key)
# kite.set_access_token(access_token)

client, config, stocks, data_manager = initialize_trading_environment(
        config_file="config.yaml",
        json_file="my_stocks.json"  # <-- You can pass any JSON file here
    )
# 🎯 List of contracts (from your instrument dump)
contracts = [
    {"symbol": "NIFTY25SEPFUT", "token": 13568258},
    {"symbol": "NIFTY25OCTFUT", "token": 13355010},
    {"symbol": "NIFTY25NOVFUT", "token": 9485826},
]

# 📂 Storage
os.makedirs("fut_data", exist_ok=True)
all_dfs = []

# ⏳ Date window (adjust as needed)
to_date = dt.datetime.now()
from_date = to_date - dt.timedelta(days=90)
interval = "30minute"
# 🔁 Loop over each expiry
for c in contracts:
    print(f"📥 Downloading {c['symbol']} ...")

    data = kite.historical_data(
        instrument_token=c["token"],
        from_date=from_date,
        to_date=to_date,
        interval=interval,
        continuous=False
    )

    df = pd.DataFrame(data)
    if not df.empty:
        df["symbol"] = c["symbol"]
        df.to_csv(f"fut_data/{c['symbol']}_{interval}.csv", index=False)
        all_dfs.append(df)
        print(f"✅ Saved {len(df)} rows for {c['symbol']}")
    else:
        print(f"⚠️ No data found for {c['symbol']}")

# 🔗 Merge into continuous contract
if all_dfs:
    continuous = pd.concat(all_dfs).sort_values("date")
    continuous.reset_index(drop=True, inplace=True)
    continuous.to_csv(f"fut_data/NIFTY_CONTINUOUS{interval}.csv", index=False)
    print(f"\n📊 Continuous contract saved with {len(continuous)} rows")
else:
    print("❌ No data available to stitch")
