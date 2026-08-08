# Data_ingestion/batch_fetch_all_fno_stocks.py
"""Fetches 2015-to-now 1-minute equity history for every NSE F&O-eligible
stock (not just the live watchlist's 50) — the full derivatives universe,
~208 stocks as of whenever this runs (recomputed live from Kite's NFO
instrument list, not hardcoded, since the F&O list changes periodically).
Skips index futures (BANKNIFTY, NIFTY, etc. — not equities) and anything
already fetched by an earlier watchlist run, to avoid redundant work.

Same chunked-fetch/timezone-safe path as historical_fetch.py's
fetch_equity_history — this is that same call, just looped over a much
bigger symbol set. Expect ~1.5-2 hours for ~158 new symbols at the
2015-depth pace observed on the watchlist run.
"""

import datetime as dt
import os

import polars as pl

from Data_ingestion.run_client import init_client
from Data_ingestion.historical_fetch import fetch_equity_history
from infrastructure.config.settings import get_settings

FROM_DATE = dt.datetime(2015, 1, 1)
OUTPUT_DIR = get_settings().historical_data_dir

# NFO 'name' values that are index futures, not equities — never valid
# arguments to the equity historical-data endpoint.
INDEX_UNDERLYINGS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}


def get_all_fno_stocks(client):
    instruments = pl.DataFrame(client.kite.instruments("NFO"))
    names = instruments.filter(pl.col("instrument_type") == "FUT")["name"].unique().sort().to_list()
    return [n for n in names if n not in INDEX_UNDERLYINGS]


def already_have_full_history(symbol: str, min_days: int = 4000) -> bool:
    path = os.path.join(OUTPUT_DIR, f"{symbol}_historical.csv")
    if not os.path.exists(path):
        return False
    # Cheap check: a 2015-deep file is much larger than the older ~22-month
    # ones ever were — avoids re-reading every CSV just to check its span.
    return os.path.getsize(path) > 20_000_000  # ~20MB, roughly the observed size at this depth


def main():
    client, _ = init_client("Data_ingestion/config.yaml")
    stocks = get_all_fno_stocks(client)
    to_date = dt.datetime.now()

    print(f"Total F&O stocks: {len(stocks)}")
    todo = [s for s in stocks if not already_have_full_history(s)]
    print(f"Already have 2015-deep history for {len(stocks) - len(todo)}; fetching {len(todo)} new ones")

    succeeded, failed = [], []
    for i, symbol in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {symbol}: fetching...")
        try:
            fetch_equity_history(client, symbol, FROM_DATE, to_date, exchange="NSE", interval="minute")
            succeeded.append(symbol)
        except Exception as e:
            print(f"[{i}/{len(todo)}] {symbol}: FAILED - {e}")
            failed.append(symbol)

    print(f"\nDone. {len(succeeded)} succeeded, {len(failed)} failed.")
    if failed:
        print("Failed:", ", ".join(failed))


if __name__ == "__main__":
    main()
