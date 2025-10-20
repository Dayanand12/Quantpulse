import os
import time
import datetime as dt
import polars as pl

def fetch_data(client, symbol, interval="5minute", output_dir="data"):
    """
    Fetch historical data (equity or futures) for a single symbol for the last 60 days.

    Parameters
    ----------
    client : KiteConnect client
    symbol : str
        Equity or futures tradingsymbol.
    interval : str
        Data interval (e.g., '1minute', '5minute', 'day', etc.)
    output_dir : str
        Directory to save CSV.

    Returns
    -------
    pl.DataFrame
        Polars DataFrame with OHLCV data.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    to_date = dt.datetime.now()
    from_date = to_date - dt.timedelta(days=60)  # last 60 days

    # Fetch instruments list
    instruments_list = client.kite.instruments()
    # Find the requested symbol
    inst = next((i for i in instruments_list if i["tradingsymbol"] == symbol), None)
    if not inst:
        raise ValueError(f"❌ Symbol {symbol} not found")

    token = inst["instrument_token"]
    expiry = inst.get("expiry")

    # Helper to fetch in 60-day chunks
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

    # Convert to Polars DataFrame
    df = pl.DataFrame(data).with_columns([
        pl.col("date").dt.convert_time_zone("Asia/Kolkata"),
        pl.lit(symbol).alias("symbol")
    ])

    if expiry:
        # Convert datetime.date to string for consistency
        if isinstance(expiry, dt.date):
            expiry = expiry.isoformat()
        df = df.with_columns(pl.lit(expiry).alias("expiry"))

    # --- ✅ Print actual data range ---
    start_date = df["date"].min()
    end_date = df["date"].max()
    print(f"📅 Data available from {start_date} to {end_date}")

    # Save CSV
    file_path = f"{output_dir}/{symbol}_{interval}.csv"
    df.write_csv(file_path)
    print(f"✅ Saved {df.height} rows → {file_path}")

    return df
