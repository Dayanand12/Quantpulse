import os
import time
import datetime as dt
import polars as pl
import pandas as pd
import requests

def fetch_data(client, symbol, interval="5minute", output_dir="data"):
    """
    Fetch historical data (equity or futures) for a single symbol for the last 60 days.
    Uses cached instruments to avoid repeated API calls.
    """
    os.makedirs(output_dir, exist_ok=True)
    cache_file = os.path.join(output_dir, "instruments_cache.csv")

    # -------------------------------
    # STEP 1️⃣ — Load or fetch instruments
    # -------------------------------
    instruments_list = None

    # Use cache if exists & updated today
    if os.path.exists(cache_file):
        modified_time = dt.datetime.fromtimestamp(os.path.getmtime(cache_file))
        if modified_time.date() == dt.datetime.now().date():
            try:
                instruments_list = pd.read_csv(cache_file).to_dict("records")
                print(f"📦 Using cached instruments ({len(instruments_list)} symbols)")
            except Exception:
                instruments_list = None

    # Fetch from API if cache missing or invalid
    if instruments_list is None:
        print("🌐 Fetching instruments from Kite API...")
        for attempt in range(3):
            try:
                instruments_list = client.kite.instruments()
                pd.DataFrame(instruments_list).to_csv(cache_file, index=False)
                print(f"✅ Instruments cached → {cache_file}")
                break
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Attempt {attempt+1} failed: {e}")
                time.sleep(3)
        else:
            raise RuntimeError("❌ Failed to fetch instruments after 3 retries.")

    # -------------------------------
    # STEP 2️⃣ — Locate instrument
    # -------------------------------
    inst = next((i for i in instruments_list if i["tradingsymbol"] == symbol), None)
    if not inst:
        raise ValueError(f"❌ Symbol {symbol} not found")

    token = inst["instrument_token"]
    expiry = inst.get("expiry")

    # -------------------------------
    # STEP 3️⃣ — Fetch historical data
    # -------------------------------
    

    def get_date_input(start_date=None, end_date=None):
        date_format = "%Y-%m-%d"
        if start_date and end_date:
            try:
                from_date = dt.datetime.strptime(start_date, date_format)
                to_date = dt.datetime.strptime(end_date, date_format)
            except ValueError:
                raise ValueError(f"Invalid date format! Use '{date_format}' (e.g. 2025-10-01)")
        else:
            to_date = dt.datetime.now()
            from_date = to_date - dt.timedelta(days=60)
        return from_date, to_date

    # Example usage:
    from_date, to_date = get_date_input("2025-10-13", "2025-10-24")

    # to_date = dt.datetime.now()
    # from_date = to_date - dt.timedelta(days=60)  # last 60 days

    def fetch_chunked(token, from_date, to_date, interval):
        data = []
        curr = from_date
        while curr < to_date:
            nxt = min(curr + dt.timedelta(days=60), to_date)
            try:
                part = client.kite.historical_data(
                    instrument_token=token,
                    from_date=curr,
                    to_date=nxt,
                    interval=interval,
                    continuous=False
                )
                data.extend(part)
            except Exception as e:
                print(f"⚠️ Error fetching {curr.date()}–{nxt.date()}: {e}")
            curr = nxt
            time.sleep(0.3)
        return data

    print(f"\n📥 Downloading {symbol} data")
    data = fetch_chunked(token, from_date, to_date, interval)

    if not data:
        print(f"⚠️ No data found for {symbol}")
        return pl.DataFrame()

    # -------------------------------
    # STEP 4️⃣ — Convert to Polars
    # -------------------------------
    df = pl.DataFrame(data).with_columns([
        pl.col("date").dt.convert_time_zone("Asia/Kolkata"),
        pl.lit(symbol).alias("symbol")
    ])

    if expiry:
        if isinstance(expiry, dt.date):
            expiry = expiry.isoformat()
        df = df.with_columns(pl.lit(expiry).alias("expiry"))

    start_date = df["date"].min()
    end_date = df["date"].max()
    print(f"📅 Data available from {start_date} to {end_date}")

    file_path = f"{output_dir}/{symbol}_{interval}.csv"
    df.write_csv(file_path)
    print(f"✅ Saved {df.height} rows → {file_path}")

    return df
