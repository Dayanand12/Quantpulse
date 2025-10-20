import os
import time
import datetime as dt
import polars as pl

def fetch_data(client, base_symbol="ULTRACEMCO", interval="5minute", output_dir="fut_data"):
    """
    Fetches and saves historical futures data (all expiries) for a given symbol from Kite Connect.

    Returns
    -------
    pl.DataFrame
        Combined continuous futures data for the given symbol and interval.
    """

    os.makedirs(output_dir, exist_ok=True)

    # Set historical window based on interval
    if interval in ["1minute", "3minute", "5minute", "10minute", "15minute"]:
        days_back = 5
    elif interval in ["30minute", "60minute"]:
        days_back = 60
    else:
        days_back = 365

    to_date = dt.datetime.now()
    from_date = to_date - dt.timedelta(days=days_back)

    # Helper function to fetch in chunks
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
                print(f"  ↳ {curr.date()} → {nxt.date()} ({len(part)} bars)")
            except Exception as e:
                print(f"  ⚠️ Error fetching {curr.date()}–{nxt.date()}: {e}")
            curr = nxt
            time.sleep(0.4)
        return data

    print("📦 Fetching instrument list ...")
    # Convert directly to Polars
    instruments_list = client.kite.instruments("NFO")
    instruments = pl.DataFrame(instruments_list)

    # Filter only FUT contracts for the given symbol
    fut_df = instruments.filter(
        pl.col("tradingsymbol").str.contains(rf"^{base_symbol}\d{{2}}[A-Z]{{3}}FUT$")
    )

    if fut_df.height == 0:
        raise ValueError(f"❌ No futures found for {base_symbol}")

    # expiry is already date type in Kite; just ensure Polars Date
    fut_df = fut_df.with_columns(pl.col("expiry").cast(pl.Date)).sort("expiry")

    print(f"✅ Found {fut_df.height} futures for {base_symbol}")

    # For intraday intervals, pick front-month unexpired contract
    if interval in ["1minute", "3minute", "5minute", "10minute", "15minute"]:
        today = dt.date.today()
        fut_df = fut_df.filter(pl.col("expiry") >= pl.lit(today))
        if fut_df.height == 0:
            raise ValueError("❌ No unexpired contracts available for intraday intervals")
        fut_df = fut_df.slice(0, 1)

    all_dfs = []

    for row in fut_df.iter_rows(named=True):
        symbol = row["tradingsymbol"]
        token = row["instrument_token"]
        expiry = row["expiry"]

        print(f"\n📥 Downloading {symbol} (Expiry: {expiry})")
        data = fetch_chunked(token, from_date, to_date, interval)

        if not data:
            print(f"⚠️ No data found for {symbol}")
            continue

        # Directly create Polars DataFrame
        df = pl.DataFrame(data)

        df = df.with_columns([
        pl.col("date").dt.replace_time_zone(None),  # make datetime naive
        pl.lit(symbol).alias("symbol"),
        pl.lit(expiry).alias("expiry")
    ])

        # Save CSV
        file_path = f"{output_dir}/{base_symbol}_{expiry}_{interval}.csv"
        df.write_csv(file_path)
        print(f"✅ Saved {df.height} rows → {file_path}")

        all_dfs.append(df)

    if all_dfs:
        continuous = pl.concat(all_dfs).sort("date")
        cont_path = f"{output_dir}/{base_symbol}_CONTINUOUS_{interval}.csv"
        continuous.write_csv(cont_path)
        print(f"\n📊 Continuous contract saved → {cont_path}")
        print(f"Total rows: {continuous.height}")
        return continuous
    else:
        print("❌ No data fetched for any contract.")
        return pl.DataFrame()
