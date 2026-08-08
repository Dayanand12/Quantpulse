# Data_ingestion/batch_fetch_watchlist_futures.py
"""One-off: fetch the current front-month futures contract for every
tradeable symbol in the live watchlist. See futures_fetch.py's docstring
for why this can only ever be a few weeks/months deep, not a long
archive — that's a Kite API ceiling (expired contracts' instrument
tokens aren't retrievable), not something this script controls.
"""

import sqlite3

from Data_ingestion.run_client import init_client
from Data_ingestion.futures_fetch import fetch_current_futures

INDEX_SYMBOLS = {"NIFTY 50", "NIFTY BANK", "INDIA VIX"}
DB_PATH = "C:/Trading/QuantPulse/data/quantpulse.db"


def get_watchlist_symbols():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM watchlist_symbols ORDER BY id")
    symbols = [r[0] for r in cur.fetchall()]
    conn.close()
    return [s for s in symbols if s not in INDEX_SYMBOLS]


def main():
    client, _ = init_client("Data_ingestion/config.yaml")
    symbols = get_watchlist_symbols()

    succeeded, failed = [], []
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}: fetching futures...")
        try:
            fetch_current_futures(client, symbol)
            succeeded.append(symbol)
        except Exception as e:
            print(f"[{i}/{len(symbols)}] {symbol}: FAILED - {e}")
            failed.append(symbol)

    print(f"\nDone. {len(succeeded)} succeeded, {len(failed)} failed.")
    if failed:
        print("Failed:", ", ".join(failed))


if __name__ == "__main__":
    main()
