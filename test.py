from kiteconnect import KiteConnect
import pandas as pd
import datetime as dt
import os

# ===============================
# CONFIG
# ===============================
api_key = "ttu1u7gc87m4g52f"
access_token = "zo3h4eyxzg8axlbettiaqamf1kpv1gy7"   # Generate via login flow
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)


kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# 🎯 List of contracts
contracts = [
    #{"symbol": "NIFTY", "token": 13568258},  # Replace with your tokens
    {"symbol": "BANKNIFTY1", "token": 1497857},
]

# ⏳ Settings
intervals = ["5minute", "15minute", "30minute"]  # Add more intervals if needed
lookback_days = 90

# 📂 Base folder for data
base_folder = "fut_data_new"
os.makedirs(base_folder, exist_ok=True)

for c in contracts:
    contract_folder = os.path.join(base_folder, c["symbol"])
    os.makedirs(contract_folder, exist_ok=True)

    for interval in intervals:
        file_path = os.path.join(contract_folder, f"{c['symbol']}_{interval}.csv")

        # Check last date in existing CSV
        if os.path.exists(file_path):
            existing_df = pd.read_csv(file_path, parse_dates=["date"])
            last_date = existing_df["date"].max()
            from_date = last_date + dt.timedelta(minutes=1)  # start after last entry
        else:
            existing_df = pd.DataFrame()
            from_date = dt.datetime.now() - dt.timedelta(days=lookback_days)

        to_date = dt.datetime.now()

        # Skip if no new data needed
        if from_date >= to_date:
            print(f"✅ {c['symbol']} ({interval}) is already up to date.")
            continue

        print(f"📥 Downloading {c['symbol']} ({interval}) from {from_date} → {to_date}")

        # Fetch historical data
        data = kite.historical_data(
            instrument_token=c["token"],
            from_date=from_date,
            to_date=to_date,
            interval=interval,
            continuous=False
        )

        df = pd.DataFrame(data)
        if df.empty:
            print(f"⚠️ No new data for {c['symbol']} ({interval})")
            continue

        # Merge with existing data and remove duplicates
        if not existing_df.empty:
            df = pd.concat([existing_df, df]).drop_duplicates(subset="date").sort_values("date")

        # Save CSV
        df.to_csv(file_path, index=False)
        print(f"✅ Saved {len(df)} rows for {c['symbol']} ({interval})\n")

