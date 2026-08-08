# Data_ingestion/futures_fetch.py
"""Fetches the current (nearest-unexpired) futures contract's full
available history for a symbol. Adapted from Data_ingestion/futures/
fut_data.py's approach (filter NFO instruments for FUT, pick front-month,
fetch chunked) — fixes a real bug found while adapting it: that script's
`.dt.replace_time_zone(None)` shifts timestamps to UTC (09:15 IST becomes
03:45) instead of stripping the tz label from the IST wall clock, the
exact bug already caught and fixed in historical_loader.py for equity
data.

Note the ceiling this is built against: Kite's instrument list only
returns currently-listed (non-expired) contracts — there's no API path to
an expired contract's instrument token, so this can only ever get however
much history the CURRENT front-month contract has had since IT was
listed (typically a few weeks to ~2 months for NSE stock futures), not a
deep multi-year archive the way equity/index data can.
"""

import datetime as dt
import os
import time

import polars as pl

from infrastructure.config.settings import get_settings


def fetch_current_futures(
    client,
    symbol: str,
    exchange: str = "NSE",
    interval: str = "minute",
    output_dir: str = None,
) -> str:
    output_dir = output_dir or os.path.join(get_settings().historical_data_dir, "futures")
    instruments = pl.DataFrame(client.kite.instruments("NFO"))
    fut = (
        instruments.filter((pl.col("name") == symbol) & (pl.col("instrument_type") == "FUT"))
        .with_columns(pl.col("expiry").cast(pl.Date))
        .sort("expiry")
    )
    if fut.height == 0:
        raise ValueError(f"No futures contracts found for {symbol}")

    today = dt.date.today()
    fut = fut.filter(pl.col("expiry") >= pl.lit(today))
    if fut.height == 0:
        raise ValueError(f"No unexpired futures contracts for {symbol}")

    row = fut.row(0, named=True)
    token = row["instrument_token"]
    tradingsymbol = row["tradingsymbol"]
    expiry = row["expiry"]

    to_date = dt.datetime.now()
    from_date = dt.datetime(2024, 10, 1)  # matches the equity data's start; the
    # contract's own listing date will naturally floor how far back real data goes

    all_candles = []
    curr = from_date
    while curr < to_date:
        chunk_end = min(curr + dt.timedelta(days=60), to_date)
        try:
            candles = client.kite.historical_data(
                instrument_token=token, from_date=curr, to_date=chunk_end,
                interval=interval, continuous=False,
            )
            all_candles.extend(candles)
        except Exception as e:
            print(f"  !! error fetching {curr.date()} to {chunk_end.date()}: {e}")
        curr = chunk_end
        time.sleep(0.4)

    if not all_candles:
        raise RuntimeError(f"No candles returned for {tradingsymbol} (expiry {expiry})")

    df = pl.DataFrame(all_candles)
    df = df.with_columns(
        pl.col("date").dt.convert_time_zone("Asia/Kolkata").dt.replace_time_zone(None)
    ).sort("date")

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{symbol}_FUT_historical.csv")
    df.write_csv(path)
    print(f"Saved {df.height} candles for {tradingsymbol} (expiry {expiry}) -> {path}")
    return path
