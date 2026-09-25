# rank_symbols_by_volatility.py
"""Ranks every symbol with a historical CSV (data/historical_data/
{symbol}_historical.csv — same convention as run_backtest.py) by a stable,
multi-week Average True Range % instead of the Stock Screener's "High
Volatility" chip, which is a single trading day's intraday snapshot
(core/domain/regime_classification.py::HIGH_VOL_ATR_PCT, recomputed live
every 3 seconds) — great for "what's moving right now," wrong for building
a watchlist meant to run for weeks: it changes every day, needs the market
open to even compute, and only covers whatever's already in a live
watchlist rather than the full universe of symbols with historical data.

For each symbol:
  1. Resample 1-minute bars to daily OHLCV.
  2. Take the most recent --lookback-days of those.
  3. Average True Range % per day (True Range as a % of that day's close),
     averaged over the window — the same *concept* as the Screener's
     atr_pct, just stabilized over weeks instead of one session.
  4. Average daily traded value (close * volume, summed per day) as a
     liquidity floor — a stock isn't tradeable-volatile just because ATR%
     is high on three trades a day; --min-daily-value excludes those.

Outputs a ranked table (top N by default) and, with --create-watchlist,
writes it straight into a named watchlist via the live app's API (so it's
immediately available to bind a deployment to — see core/domain/
models.py::Deployment's watchlist_id).

Examples:
    python rank_symbols_by_volatility.py
    python rank_symbols_by_volatility.py --top 50 --lookback-days 60 --min-daily-value 10_00_00_000
    python rank_symbols_by_volatility.py --top 40 --create-watchlist "High Volatility"
"""

import argparse
import glob
import os
import re
import sys
from typing import List, Optional

import polars as pl
import requests

# Windows' default console codepage (cp1252) can't render polars' own
# Unicode table borders or a ₹ sign — reconfigure stdout to UTF-8 so this
# runs the same from a plain cmd.exe window as it does here, regardless of
# how the caller invokes it.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from infrastructure.config.settings import get_settings
from runners.backtesting.historical_loader import load_equity_csv

DEFAULT_LOOKBACK_DAYS = 60
DEFAULT_MIN_DAILY_VALUE = 10_00_00_000  # ₹10 crore/day
DEFAULT_TOP_N = 50
LIVE_API_BASE = "http://127.0.0.1:5000"


def discover_symbols(historical_data_dir: str) -> List[str]:
    pattern = os.path.join(historical_data_dir, "*_historical.csv")
    symbols = []
    for path in glob.glob(pattern):
        name = os.path.basename(path)
        symbols.append(re.sub(r"_historical\.csv$", "", name))
    return sorted(symbols)


def daily_atr_pct_and_value(df: pl.DataFrame, lookback_days: int) -> Optional[dict]:
    """df: 1-minute bars (load_equity_csv's shape). Returns None if there
    isn't at least lookback_days of daily data to work with."""
    daily = (
        df.with_columns(pl.col("date").dt.date().alias("day"))
        .group_by("day", maintain_order=True)
        .agg(
            pl.col("open").first(),
            pl.col("high").max(),
            pl.col("low").min(),
            pl.col("close").last(),
            pl.col("volume").sum(),
        )
        .sort("day")
    )

    if daily.height < lookback_days + 1:
        return None  # not enough history to fill the window at all

    daily = daily.tail(lookback_days + 1)  # +1 so the first row has a prev_close for True Range

    daily = daily.with_columns(pl.col("close").shift(1).alias("prev_close")).slice(1)

    true_range = pl.max_horizontal(
        pl.col("high") - pl.col("low"),
        (pl.col("high") - pl.col("prev_close")).abs(),
        (pl.col("low") - pl.col("prev_close")).abs(),
    )
    daily = daily.with_columns(
        true_range.alias("true_range"),
        (pl.col("close") * pl.col("volume")).alias("traded_value"),
    )
    daily = daily.with_columns((pl.col("true_range") / pl.col("close") * 100).alias("atr_pct"))

    return {
        "avg_atr_pct": float(daily["atr_pct"].mean()),
        "avg_daily_value": float(daily["traded_value"].mean()),
        "days_covered": daily.height,
        "last_close": float(daily["close"][-1]),
    }


def rank_symbols(
    historical_data_dir: str, lookback_days: int, min_daily_value: float
) -> pl.DataFrame:
    symbols = discover_symbols(historical_data_dir)
    rows = []

    for i, symbol in enumerate(symbols, 1):
        path = os.path.join(historical_data_dir, f"{symbol}_historical.csv")
        print(f"[{i}/{len(symbols)}] {symbol}...", end=" ", flush=True)
        try:
            df = load_equity_csv(path)
        except Exception as e:
            print(f"skip (read error: {e})")
            continue

        stats = daily_atr_pct_and_value(df, lookback_days)
        if stats is None:
            print(f"skip (only {df.height} bars, not enough history)")
            continue

        print(f"ATR% {stats['avg_atr_pct']:.2f}, avg value Rs {stats['avg_daily_value']:,.0f}/day")
        rows.append({"symbol": symbol, **stats})

    result = pl.DataFrame(rows)
    result = result.filter(pl.col("avg_daily_value") >= min_daily_value)
    return result.sort("avg_atr_pct", descending=True)


def create_watchlist(name: str, symbols: List[str]) -> None:
    resp = requests.post(f"{LIVE_API_BASE}/api/watchlists", json={"name": name}, timeout=10)
    if resp.status_code == 400:
        # Name already taken — reuse the existing one instead of failing.
        existing = requests.get(f"{LIVE_API_BASE}/api/watchlists", timeout=10).json()
        match = next((w for w in existing if w["name"] == name), None)
        if match is None:
            resp.raise_for_status()
        watchlist_id = match["id"]
    else:
        resp.raise_for_status()
        watchlist_id = resp.json()["id"]

    resp = requests.put(
        f"{LIVE_API_BASE}/api/watchlists/{watchlist_id}/symbols",
        json={"symbols": symbols},
        timeout=30,
    )
    resp.raise_for_status()
    print(f"\nWatchlist {name!r} (id={watchlist_id}) now holds {len(symbols)} symbols.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--min-daily-value", type=float, default=DEFAULT_MIN_DAILY_VALUE)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    parser.add_argument(
        "--create-watchlist",
        metavar="NAME",
        help="Also write the top N symbols into this named watchlist via the live app's API "
        "(POST/PUT /api/watchlists — requires run_live.py/run_all.py running on port 5000).",
    )
    args = parser.parse_args()

    historical_data_dir = get_settings().historical_data_dir
    ranked = rank_symbols(historical_data_dir, args.lookback_days, args.min_daily_value)

    top = ranked.head(args.top)

    print(f"\n=== Top {len(top)} by {args.lookback_days}-day avg ATR% (min Rs {args.min_daily_value:,.0f}/day traded value) ===")
    with pl.Config(tbl_rows=-1, fmt_str_lengths=20):
        print(
            top.select(
                "symbol",
                pl.col("avg_atr_pct").round(2),
                pl.col("avg_daily_value").round(0).alias("avg_daily_value_rs"),
                "days_covered",
                pl.col("last_close").round(2),
            )
        )

    if args.create_watchlist:
        create_watchlist(args.create_watchlist, top["symbol"].to_list())


if __name__ == "__main__":
    main()
