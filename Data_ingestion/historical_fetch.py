# Data_ingestion/historical_fetch.py
"""Fetches a symbol's full 1-minute equity history and writes it as
{SYMBOL}_historical.csv under settings.historical_data_dir — but chunked,
since Kite's historical-data endpoint caps how much range a single call
can cover (conservatively 60 days here, matching Data_ingestion/futures/
fut_data.py's own chunking convention, safe across every interval Kite
offers).

historical_data_dir defaults to a non-OneDrive-synced path (see
infrastructure/config/settings.py) — these files grow into the
multi-GB range across a few hundred symbols' multi-year 1-minute
history, and OneDrive continuously trying to sync that in the
background is what forced moving it there in the first place.
"""

import os
import time
import datetime as dt

import polars as pl

from infrastructure.config.settings import get_settings

_CHUNK_DAYS = 60


def fetch_equity_history(
    client,
    symbol: str,
    from_date: dt.datetime,
    to_date: dt.datetime,
    exchange: str = "NSE",
    interval: str = "minute",
    output_dir: str = None,
) -> str:
    output_dir = output_dir or get_settings().historical_data_dir
    os.makedirs(output_dir, exist_ok=True)

    all_candles = []
    curr = from_date
    while curr < to_date:
        chunk_end = min(curr + dt.timedelta(days=_CHUNK_DAYS), to_date)
        try:
            candles = client.fetch_historical_data(
                symbol=symbol, interval=interval, from_date=curr, to_date=chunk_end, exchange=exchange
            )
            all_candles.extend(candles)
            print(f"  -> {curr.date()} to {chunk_end.date()}: {len(candles)} bars")
        except Exception as e:
            print(f"  !! error fetching {curr.date()} to {chunk_end.date()}: {e}")
        curr = chunk_end
        time.sleep(0.4)  # stay well under Kite's rate limit across chunks

    if not all_candles:
        raise RuntimeError(f"No candles returned for {symbol} in [{from_date}, {to_date}]")

    df = pl.DataFrame(all_candles).sort("date")
    path = os.path.join(output_dir, f"{symbol}_historical.csv")
    df.write_csv(path)
    print(f"Saved {df.height} candles for {symbol} -> {path}")
    return path
