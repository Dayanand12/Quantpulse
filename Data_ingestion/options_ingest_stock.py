# Data_ingestion/options_ingest_stock.py
"""Normalizes the stock-options archive (per-contract 1-minute OHLCV+OI CSVs,
sourced from a third party -- see the Phase 0 validation writeup: tick-size,
cross-strike, and underlying-correlation checks all confirmed this is real
exchange-derived data, not synthetic) into the same per-contract-CSV layout
`historical_data_dir` already uses for equity/futures data.

Two source archives cover different, only partially-overlapping windows for
the same contract universe -- "stock options.zip" is the broad A-Z archive
but stops around 2026-04-28 expiries; the numbered "drive-download-*.zip"
parts only cover a P-T alphabetical slice but extend to 2026-07-28. Where
both have the exact same contract file, content is byte-identical (verified
during the audit), so this is a simple union of file paths across sources,
not a row-level merge.

Cleaning applied per contract:
  - drop rows whose date isn't a real NSE trading day, per a calendar
    derived from RELIANCE's own already-trusted equity history rather than
    trusted blindly from the option data itself. Note: an early version of
    this audit flagged HDFCAMC_2900_CE's session on Sunday 2026-02-01 as a
    suspected bogus/synthetic row -- it isn't. RELIANCE's own equity feed
    has a full, actively-traded 375-bar session that same Sunday (real
    volume, real price discovery, in line with neighboring days), so NSE
    evidently ran a special live session that day (Union Budget day
    special sessions are a known real-world precedent) and both datasets
    correctly captured it. The trading calendar below includes it.
  - drop rows outside real market hours (09:15-15:30 IST).
  - dedupe exact-duplicate timestamps, sorted ascending.

Output timestamp is stored already as IST-naive wall clock (unlike the
equity CSVs, which store raw UTC and convert at load time in
historical_loader.py) -- the source data's "+05:30" offset is constant, so
there's nothing to convert at load time and a future load_option_csv can
just parse the column directly.
"""

import io
import os
import zipfile
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

import polars as pl

from infrastructure.config.settings import get_settings

GUJRAT_DIR = r"C:\Trading\Historycal_data\gujrat"

DEFAULT_SOURCES = [os.path.join(GUJRAT_DIR, "stock options.zip")] + [
    os.path.join(GUJRAT_DIR, f"drive-download-20260807T180000Z-1-{i:03d}.zip") for i in range(1, 10)
]

MARKET_OPEN = "09:15:00"
MARKET_CLOSE = "15:30:00"


@dataclass
class ContractManifestRow:
    underlying: str
    expiry: str
    strike: float
    side: str
    source_path: str
    rows_raw: int
    rows_kept: int
    dropped_non_trading_day: int
    dropped_off_hours: int
    dropped_duplicate_ts: int
    dropped_malformed: int
    first_date: Optional[str]
    last_date: Optional[str]
    reaches_expiry_close: bool


def _parse_relative_path(rel_path: str) -> Optional[Tuple[str, str, float, str]]:
    """'<UNDERLYING>/<EXPIRY>/<fname>.csv' -> (underlying, expiry, strike, side).
    fname is '{SYM}_{STRIKE}_{SIDE}_{DD}_{MON}_{YY}' -- split from the right
    so tickers containing '&' or '-' (M&M, BAJAJ-AUTO) parse fine regardless.
    """
    parts = rel_path.split("/")
    if len(parts) != 3 or not parts[2].endswith(".csv"):
        return None
    underlying, expiry = parts[0], parts[1]
    fname = parts[2][: -len(".csv")]
    tokens = fname.split("_")
    if len(tokens) < 6:
        return None
    strike_tok, side_tok = tokens[-5], tokens[-4]
    try:
        strike = float(strike_tok)
    except ValueError:
        return None
    if side_tok not in ("CE", "PE"):
        return None
    return underlying, expiry, strike, side_tok


def build_trading_calendar(reference_csv: str) -> set:
    df = pl.read_csv(reference_csv, try_parse_dates=True, columns=["date"])
    dates = df["date"].dt.convert_time_zone("Asia/Kolkata").dt.date().unique()
    return set(dates.to_list())


def _index_sources(source_paths: List[str]) -> Dict[str, str]:
    """relative csv path -> the source zip that has it (first one wins;
    content is identical where more than one source has the same path)."""
    path_to_source: Dict[str, str] = {}
    for path in source_paths:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.endswith(".csv") and name not in path_to_source:
                    path_to_source[name] = path
    return path_to_source


def _clean_contract(raw: pl.DataFrame, valid_dates: set) -> Tuple[pl.DataFrame, dict]:
    n_raw = raw.height
    if n_raw == 0:
        return raw, {
            "dropped_non_trading_day": 0,
            "dropped_off_hours": 0,
            "dropped_duplicate_ts": 0,
            "dropped_malformed": 0,
        }

    # strict=False: a handful of rows across ~260k files have a garbled
    # (blank/truncated) timestamp field -- not worth failing the whole
    # backfill over a few corrupt source rows, so they become null and get
    # dropped explicitly below (counted, not silently discarded).
    df = raw.with_columns(
        pl.col("timestamp").str.slice(0, 19).str.to_datetime("%Y-%m-%dT%H:%M:%S", strict=False)
    ).sort("timestamp")

    before = df.height
    df = df.filter(pl.col("timestamp").is_not_null())
    dropped_malformed = before - df.height

    before = df.height
    df = df.filter(pl.col("timestamp").dt.date().is_in(list(valid_dates)))
    dropped_calendar = before - df.height

    before = df.height
    df = df.filter(
        (pl.col("timestamp").dt.strftime("%H:%M:%S") >= MARKET_OPEN)
        & (pl.col("timestamp").dt.strftime("%H:%M:%S") <= MARKET_CLOSE)
    )
    dropped_hours = before - df.height

    before = df.height
    df = df.unique(subset=["timestamp"], keep="first").sort("timestamp")
    dropped_dupe = before - df.height

    df = df.rename({"timestamp": "date"})
    return df, {
        "dropped_non_trading_day": dropped_calendar,
        "dropped_off_hours": dropped_hours,
        "dropped_duplicate_ts": dropped_dupe,
        "dropped_malformed": dropped_malformed,
    }


def ingest_stock_options(
    underlyings: Optional[List[str]] = None,
    source_paths: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    calendar_reference_csv: Optional[str] = None,
) -> str:
    """underlyings=None processes every underlying found across all sources.
    Returns the path to the written manifest CSV."""
    source_paths = source_paths or DEFAULT_SOURCES
    output_dir = output_dir or os.path.join(get_settings().historical_data_dir, "options", "stocks")
    calendar_reference_csv = calendar_reference_csv or os.path.join(
        get_settings().historical_data_dir, "RELIANCE_historical.csv"
    )

    valid_dates = build_trading_calendar(calendar_reference_csv)
    print(f"trading calendar: {len(valid_dates)} valid days ({min(valid_dates)} .. {max(valid_dates)})")

    print("indexing source archives...")
    path_to_source = _index_sources(source_paths)
    print(f"  {len(path_to_source)} unique contract files across {len(source_paths)} sources")

    manifest: List[ContractManifestRow] = []
    open_zips: Dict[str, zipfile.ZipFile] = {}

    n_written = 0
    n_skipped_empty = 0
    n_errors = 0
    for rel_path, source in sorted(path_to_source.items()):
        parsed = _parse_relative_path(rel_path)
        if parsed is None:
            continue
        underlying, expiry, strike, side = parsed
        if underlyings is not None and underlying not in underlyings:
            continue

        try:
            if source not in open_zips:
                open_zips[source] = zipfile.ZipFile(source)
            z = open_zips[source]

            with z.open(rel_path) as f:
                raw_bytes = f.read()
            if len(raw_bytes) < 40:  # header-only / empty
                n_skipped_empty += 1
                continue
            raw = pl.read_csv(io.BytesIO(raw_bytes))

            cleaned, drop_stats = _clean_contract(raw, valid_dates)
            if cleaned.height == 0:
                n_skipped_empty += 1
                continue

            contract_dir = os.path.join(output_dir, underlying, expiry)
            os.makedirs(contract_dir, exist_ok=True)
            strike_label = f"{strike:g}"
            out_path = os.path.join(contract_dir, f"{underlying}_{strike_label}_{side}.csv")
            cleaned.write_csv(out_path)
            n_written += 1

            first_date = cleaned["date"][0]
            last_date = cleaned["date"][-1]
            manifest.append(
                ContractManifestRow(
                    underlying=underlying,
                    expiry=expiry,
                    strike=strike,
                    side=side,
                    source_path=rel_path,
                    rows_raw=raw.height,
                    rows_kept=cleaned.height,
                    dropped_non_trading_day=drop_stats["dropped_non_trading_day"],
                    dropped_off_hours=drop_stats["dropped_off_hours"],
                    dropped_duplicate_ts=drop_stats["dropped_duplicate_ts"],
                    dropped_malformed=drop_stats["dropped_malformed"],
                    first_date=str(first_date),
                    last_date=str(last_date),
                    reaches_expiry_close=str(last_date.date()) == expiry,
                )
            )
        except Exception as e:  # noqa: BLE001 -- one bad contract file must not kill a ~260k-file backfill
            n_errors += 1
            print(f"  !! {rel_path}: {e}")
            continue

        if n_written % 2000 == 0:
            print(f"  ... {n_written} contracts written, {n_skipped_empty} skipped (empty), {n_errors} errors")

    for z in open_zips.values():
        z.close()

    manifest_df = pl.DataFrame([asdict(m) for m in manifest])
    manifest_path = os.path.join(output_dir, "_ingest_manifest.csv")
    manifest_df.write_csv(manifest_path)

    print(f"\nDone. {n_written} contracts written, {n_skipped_empty} empty/skipped, {n_errors} errors.")
    print(f"manifest -> {manifest_path}")
    return manifest_path


if __name__ == "__main__":
    import sys

    only = sys.argv[1:] or None
    ingest_stock_options(underlyings=only)
