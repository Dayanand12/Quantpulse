# Data_ingestion/batch_fetch_watchlist.py
"""One-off: fetch full 1-minute equity history for every tradeable symbol
in the live watchlist (skips index symbols, which aren't fetchable the
same way and aren't what any deployment actually trades), so backtests can
run across the whole watchlist instead of just the one research symbol
(ABB) fetched so far. Skips a symbol if its CSV already covers close to
the requested range, so re-runs are cheap.
"""

import datetime as dt
import os
import sqlite3

from Data_ingestion.run_client import init_client
from Data_ingestion.historical_fetch import fetch_equity_history
from infrastructure.config.settings import get_settings

INDEX_SYMBOLS = {"NIFTY 50", "NIFTY BANK", "INDIA VIX"}
DB_PATH = "C:/Trading/QuantPulse/data/quantpulse.db"
OUTPUT_DIR = get_settings().historical_data_dir
FROM_DATE = dt.datetime(2024, 10, 1)


def get_watchlist_symbols():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM watchlist_symbols ORDER BY id")
    symbols = [r[0] for r in cur.fetchall()]
    conn.close()
    return [s for s in symbols if s not in INDEX_SYMBOLS]


def already_fetched(symbol: str, to_date: dt.datetime, min_days: int = 500) -> bool:
    path = os.path.join(OUTPUT_DIR, f"{symbol}_historical.csv")
    if not os.path.exists(path):
        return False
    # Cheap check: file covers close to the full requested range if it's
    # been more than min_days since from_date and the file is non-trivial.
    size = os.path.getsize(path)
    span_days = (to_date - FROM_DATE).days
    return span_days >= min_days and size > 5_000_000  # ~5MB, roughly ABB's size for a full fetch


def main():
    client, _ = init_client("Data_ingestion/config.yaml")
    symbols = get_watchlist_symbols()
    to_date = dt.datetime.now()

    print(f"Fetching {len(symbols)} symbols from {FROM_DATE.date()} to {to_date.date()}")

    for i, symbol in enumerate(symbols, 1):
        if already_fetched(symbol, to_date):
            print(f"[{i}/{len(symbols)}] {symbol}: already fetched, skipping")
            continue

        print(f"[{i}/{len(symbols)}] {symbol}: fetching...")
        try:
            fetch_equity_history(client, symbol, FROM_DATE, to_date, exchange="NSE", interval="minute")
        except Exception as e:
            print(f"[{i}/{len(symbols)}] {symbol}: FAILED - {e}")

    print("Done.")


if __name__ == "__main__":
    main()
