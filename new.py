from kiteconnect import KiteConnect
import pandas as pd
import datetime as dt
import os

api_key = "1bfpnkeo1p80nft7"
access_token = "RKdYwfIl0tUGjqOfOfsvZJjJCL7UzPwP"   # Generate via login flow

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# 📂 Storage
os.makedirs("fut_data", exist_ok=True)
all_dfs = []

interval = "30minute"  # use "day" if you want daily first (much faster)

# 🔎 Load instrument list
instruments = kite.instruments("NFO")
instruments_df = pd.DataFrame(instruments)

# 🎯 Filter only NIFTY futures
nifty_futs = instruments_df[
    (instruments_df["name"] == "NIFTY") &
    (instruments_df["segment"] == "NFO-FUT")
][["tradingsymbol", "instrument_token", "expiry"]].drop_duplicates()

# 📌 Filter contracts for last 2 years
start_date = dt.date.today() - dt.timedelta(days=730)
nifty_futs = nifty_futs[nifty_futs["expiry"] >= start_date]

print("📋 Contracts selected:")
print(nifty_futs)

# 🔁 Download each contract’s full life
for _, row in nifty_futs.iterrows():
    symbol = row["tradingsymbol"]
    token = row["instrument_token"]
    expiry = row["expiry"]

    from_date = expiry - dt.timedelta(days=90)  # approx listing
    to_date = expiry

    # Zerodha API max = 60 days per call, so batch fetch
    batch_start = from_date
    dfs = []
    while batch_start < to_date:
        batch_end = min(batch_start + dt.timedelta(days=60), to_date)
        print(f"📥 {symbol}: {batch_start} → {batch_end}")

        data = kite.historical_data(
            instrument_token=token,
            from_date=batch_start,
            to_date=batch_end,
            interval=interval,
            continuous=False
        )
        if data:
            dfs.append(pd.DataFrame(data))
        batch_start = batch_end + dt.timedelta(days=1)

    if dfs:
        df = pd.concat(dfs)
        df["symbol"] = symbol
        df.to_csv(f"fut_data/{symbol}_{interval}.csv", index=False)
        all_dfs.append(df)
        print(f"✅ Saved {len(df)} rows for {symbol}")
    else:
        print(f"⚠️ No data for {symbol}")

# 🔗 Merge into continuous contract
if all_dfs:
    continuous = pd.concat(all_dfs).sort_values("date")
    continuous.reset_index(drop=True, inplace=True)
    continuous.to_csv(f"fut_data/NIFTY_CONTINUOUS_{interval}_2Y.csv", index=False)
    print(f"\n📊 Continuous contract saved with {len(continuous)} rows")
else:
    print("❌ No data available to stitch")
