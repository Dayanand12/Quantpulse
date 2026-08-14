# Data_ingestion/options_ingest_index.py
"""Normalizes the index-options tick archives (NIFTY/BANKNIFTY, one parquet
per trading day covering the whole chain that day: timestamp,price,volume,
tradingsymbol,instrument_type,expiry,strike,segment,index_name) into the
same per-contract 1-minute-bar CSV layout options_ingest_stock.py produces
for stock options, so both instrument classes converge on one shape before
they ever reach the backtest engine.

A contract's history spans many day-files (one per trading day until it
expires), so this streams day-by-day and *appends* each day's resampled
bars to that contract's growing output CSV, rather than holding the whole
multi-year tick history in memory.

The source "volume" field's exact semantics are NOT reliably known. Kite's
own tick schema calls this `volume_traded` (cumulative for the day), which
matches this codebase's live-feed code (Data_ingestion/client.py reads
tick.get("volume_traded")) and matches most of a day's behaviour here
(flat, then step increases) -- but it also shows real *decreases* late in
the day for at least one verified contract, which plain cumulative volume
cannot do. Rather than guess and fabricate a "volume traded this minute"
number via diff() (which would silently produce nonsense negative values
on exactly the contracts where the field misbehaves), this stores the raw
last-observed value per minute verbatim as `volume`, plus an unambiguous
`tick_count` liquidity signal, and leaves resolving the field's true
meaning for whenever something actually depends on it.

No OI is available from this source (unlike the stock-options data) -- the
`oi` column is written as 0 for schema parity with the stock CSVs, not as
a real observation.
"""

import io
import os
import zipfile
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import polars as pl

from infrastructure.config.settings import get_settings

MARKET_OPEN = "09:15:00"
MARKET_CLOSE = "15:30:00"

DEFAULT_SOURCES = {
    "NIFTY": {"kind": "zip", "path": r"C:\Trading\Historycal_data\NIFTY-20260802T052807Z-1-001.zip"},
    "BANKNIFTY": {"kind": "dir", "path": r"C:\Trading\Historycal_data\BANKNIFTY-20260802T055137Z-1-001\BANKNIFTY"},
}

# A second, broader archive that happens to carry several indices' ticks
# together in one file per day (day-folder/ALL_INDICES_TICK_DATA_<date>.
# parquet, same timestamp/price/volume/tradingsymbol/instrument_type/
# expiry/strike/segment/index_name columns _resample_day already expects —
# just multiple index_name values mixed into one file instead of one file
# per index). Its day coverage only partially overlaps DEFAULT_SOURCES'
# per-index archives, so running this AFTER the primary source (see
# skip_existing_days in ingest_index_options) recovers real days the
# primary archive is simply missing, e.g. NIFTY's zip only ever had ~120
# of the ~650 trading days since 2023-11 -- this fills in a large chunk of
# the rest from data that was already sitting on disk.
FALLBACK_MULTI_INDEX_SOURCE = {
    "kind": "multi_index_dir",
    "path": r"C:\Trading\Historycal_data\ALL_DATA-20260802T060910Z-1-002\ALL_DATA",
    "file_prefix": "ALL_INDICES_TICK_DATA",
}


@dataclass
class DayManifestRow:
    index_name: str
    day: str
    status: str  # "ok" | "empty" | "error"
    tick_rows: int
    contracts: int
    detail: str = ""


def _resample_day(raw: pl.DataFrame) -> pl.DataFrame:
    """raw: timestamp,price,volume,instrument_type,expiry,strike (one day,
    one index, every strike/expiry mixed together) -> one row per
    (expiry, strike, instrument_type, minute)."""
    df = raw.filter(pl.col("instrument_type").is_in(["CE", "PE"])).sort("timestamp")
    df = df.filter(
        (pl.col("timestamp").dt.strftime("%H:%M:%S") >= MARKET_OPEN)
        & (pl.col("timestamp").dt.strftime("%H:%M:%S") <= MARKET_CLOSE)
    )
    if df.height == 0:
        return df

    df = df.with_columns(pl.col("timestamp").dt.truncate("1m").alias("minute"))
    bars = (
        df.group_by(["expiry", "strike", "instrument_type", "minute"])
        .agg(
            pl.col("price").first().alias("open"),
            pl.col("price").max().alias("high"),
            pl.col("price").min().alias("low"),
            pl.col("price").last().alias("close"),
            pl.col("volume").last().alias("volume"),
            pl.len().alias("tick_count"),
        )
        .sort(["expiry", "strike", "instrument_type", "minute"])
        .rename({"minute": "date"})
    )
    return bars


def _append_contract_bars(bars: pl.DataFrame, index_name: str, output_dir: str) -> int:
    n_contracts = 0
    for (expiry, strike, side), group in bars.group_by(["expiry", "strike", "instrument_type"]):
        expiry_str = str(expiry)
        strike_label = f"{strike:g}"
        contract_dir = os.path.join(output_dir, index_name, expiry_str)
        os.makedirs(contract_dir, exist_ok=True)
        out_path = os.path.join(contract_dir, f"{index_name}_{strike_label}_{side}.csv")

        out = group.select(["date", "open", "high", "low", "close", "volume", "tick_count"]).with_columns(
            pl.lit(0).alias("oi")
        )
        file_exists = os.path.exists(out_path)
        csv_text = out.write_csv(include_header=not file_exists)
        with open(out_path, "a", encoding="utf-8", newline="") as f:
            f.write(csv_text)
        n_contracts += 1
    return n_contracts


def _read_parquet_safely(path_or_bytes) -> Optional[pl.DataFrame]:
    """A day-file that's physically truncated/corrupted (seen in practice:
    "Dictionary Index is out-of-bounds" from a partial sync of these
    multi-GB archives) must not kill the whole backfill just because it
    happened to be day 101 of 130 -- every OTHER call site in this module
    already tolerates a bad/missing day via try/except, this closes the
    one gap where the read itself (not _resample_day/_append_contract_
    bars) was the thing that could raise, outside any of those guards."""
    try:
        return pl.read_parquet(path_or_bytes)
    except Exception as e:  # noqa: BLE001 -- see docstring
        print(f"  !! unreadable parquet file, treating as empty: {e}")
        return None


def _iter_day_frames(index_name: str, source: dict):
    if source["kind"] == "dir":
        base = source["path"]
        for day in sorted(os.listdir(base)):
            day_dir = os.path.join(base, day)
            files = [f for f in os.listdir(day_dir) if f.endswith(".parquet")]
            if not files:
                yield day, None
                continue
            yield day, _read_parquet_safely(os.path.join(day_dir, files[0]))
    elif source["kind"] == "zip":
        with zipfile.ZipFile(source["path"]) as z:
            parquet_names = sorted(n for n in z.namelist() if n.endswith(".parquet"))
            days_seen = set()
            for name in parquet_names:
                day = name.split("/")[1]
                days_seen.add(day)
                with z.open(name) as f:
                    yield day, _read_parquet_safely(io.BytesIO(f.read()))
            # zip only lists directory entries for days that HAVE a file when
            # namelist() is filtered to .parquet above, so no separate
            # "empty day" pass is needed here (unlike the dir case).
    elif source["kind"] == "multi_index_dir":
        # See FALLBACK_MULTI_INDEX_SOURCE -- one file per day holds every
        # index's ticks mixed together, so filter down to just this
        # index_name before it reaches _resample_day (which assumes a
        # single-index frame, same as the zip/dir sources already hand it).
        base = source["path"]
        prefix = source.get("file_prefix", "ALL_INDICES_TICK_DATA")
        for day in sorted(os.listdir(base)):
            day_dir = os.path.join(base, day)
            if not os.path.isdir(day_dir):
                continue
            files = [f for f in os.listdir(day_dir) if f.startswith(prefix) and f.endswith(".parquet")]
            if not files:
                yield day, None
                continue
            raw = _read_parquet_safely(os.path.join(day_dir, files[0]))
            yield day, (raw.filter(pl.col("index_name") == index_name) if raw is not None else None)
    else:
        raise ValueError(f"unknown source kind: {source['kind']}")


def ingest_index_options(
    indices: Optional[List[str]] = None,
    sources: Optional[Dict[str, dict]] = None,
    output_dir: Optional[str] = None,
    limit_days: Optional[int] = None,
    skip_existing_days: bool = True,
) -> str:
    """skip_existing_days (default True): a day already recorded "ok" in
    output_dir's existing manifest is never reprocessed, regardless of
    which source produced it. This matters most for running a SECOND
    source (see FALLBACK_MULTI_INDEX_SOURCE) against an index that
    already has real ingested days from a first run -- _append_contract_
    bars always APPENDS, so reprocessing an already-done day would
    silently double every bar for that day in the contract's CSV rather
    than erroring. The manifest itself is merged, not overwritten: rows
    for days this run skipped or never touched are carried forward
    unchanged, so a second, third, ... run against different sources
    keeps one running history instead of each run erasing the last one's.
    """
    sources = sources or DEFAULT_SOURCES
    output_dir = output_dir or os.path.join(get_settings().historical_data_dir, "options", "index")
    indices = indices or list(sources.keys())

    manifest_path = os.path.join(output_dir, "_ingest_manifest.csv")
    old_manifest_df = pl.read_csv(manifest_path) if os.path.exists(manifest_path) else None

    manifest: List[DayManifestRow] = []

    for index_name in indices:
        source = sources[index_name]
        print(f"=== {index_name} ({source['kind']}: {source['path']}) ===")

        already_ok_days: set = set()
        if skip_existing_days and old_manifest_df is not None:
            already_ok_days = set(
                old_manifest_df.filter(
                    (pl.col("index_name") == index_name) & (pl.col("status") == "ok")
                )["day"].to_list()
            )

        n_days = 0
        n_skipped = 0
        for day, raw in _iter_day_frames(index_name, source):
            if limit_days is not None and n_days >= limit_days:
                break
            n_days += 1

            if day in already_ok_days:
                n_skipped += 1
                continue

            if raw is None or raw.height == 0:
                manifest.append(DayManifestRow(index_name, day, "empty", 0, 0))
                continue
            try:
                bars = _resample_day(raw)
                if bars.height == 0:
                    manifest.append(DayManifestRow(index_name, day, "empty", raw.height, 0))
                    continue
                n_contracts = _append_contract_bars(bars, index_name, output_dir)
                manifest.append(DayManifestRow(index_name, day, "ok", raw.height, n_contracts))
            except Exception as e:  # noqa: BLE001 -- one bad day must not kill the whole backfill
                manifest.append(DayManifestRow(index_name, day, "error", raw.height, 0, detail=str(e)))
                print(f"  !! {day}: {e}")

            if n_days % 25 == 0:
                print(f"  ... {n_days} days processed ({n_skipped} skipped, already ingested)")

        print(f"  {index_name}: {n_days} day-files seen, {n_skipped} skipped (already ingested), "
              f"{n_days - n_skipped} newly processed")

    os.makedirs(output_dir, exist_ok=True)
    if manifest:
        new_manifest_df = pl.DataFrame([asdict(m) for m in manifest])
        if old_manifest_df is not None:
            old_kept = old_manifest_df.join(
                new_manifest_df.select(["index_name", "day"]), on=["index_name", "day"], how="anti"
            )
            final_df = pl.concat([old_kept, new_manifest_df], how="vertical")
        else:
            final_df = new_manifest_df
    else:
        final_df = old_manifest_df if old_manifest_df is not None else pl.DataFrame([asdict(m) for m in manifest])

    final_df = final_df.sort(["index_name", "day"])
    final_df.write_csv(manifest_path)
    print(f"\nmanifest -> {manifest_path}")
    return manifest_path


if __name__ == "__main__":
    import sys

    only = sys.argv[1:] or None
    ingest_index_options(indices=only)
