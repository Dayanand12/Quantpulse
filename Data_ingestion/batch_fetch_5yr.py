# Data_ingestion/batch_fetch_5yr.py
"""One-off: re-fetch 5 years of 1-minute history (instead of the ~22
months fetched earlier) for every watchlist symbol plus the 3 index
symbols. Confirmed empirically (see conversation) that Kite's minute-
interval data actually goes back at least 5 years with no gaps — this
isn't chunking-limited the way a single request is, just a deeper
from_date through the same chunked fetch_equity_history() path.
Overwrites the existing (shallower) files — strict superset, no data lost.
"""

import datetime as dt
import sqlite3

from Data_ingestion.run_client import init_client
from Data_ingestion.historical_fetch import fetch_equity_history

INDEX_SYMBOLS = ["NIFTY 50", "NIFTY BANK", "INDIA VIX"]
DB_PATH = "C:/Trading/QuantPulse/data/quantpulse.db"
FROM_DATE = dt.datetime(2021, 8, 1)


def get_watchlist_symbols():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM watchlist_symbols ORDER BY id")
    symbols = [r[0] for r in cur.fetchall()]
    conn.close()
    return [s for s in symbols if s not in INDEX_SYMBOLS]


def main():
    client, _ = init_client("Data_ingestion/config.yaml")
    symbols = INDEX_SYMBOLS + get_watchlist_symbols()
    to_date = dt.datetime.now()

    print(f"Fetching {len(symbols)} symbols from {FROM_DATE.date()} to {to_date.date()} (~5 years)")

    succeeded, failed = [], []
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}: fetching...")
        try:
            fetch_equity_history(client, symbol, FROM_DATE, to_date, exchange="NSE", interval="minute")
            succeeded.append(symbol)
        except Exception as e:
            print(f"[{i}/{len(symbols)}] {symbol}: FAILED - {e}")
            failed.append(symbol)

    print(f"\nDone. {len(succeeded)} succeeded, {len(failed)} failed.")
    if failed:
        print("Failed:", ", ".join(failed))


if __name__ == "__main__":
    main()
