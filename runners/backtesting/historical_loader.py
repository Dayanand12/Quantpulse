# runners/backtesting/historical_loader.py
"""Reads a Data_ingestion-style equity OHLCV CSV (date,open,high,low,close,
volume — see Data_ingestion/run_client.py::fetch_historical) into the same
schema LiveEngine keeps in `self.data[symbol]`, so every downstream piece
(resampling, indicator calc) works unmodified on either live or historical
candles.
"""

import datetime as dt
import os
from typing import Dict, List, Optional

import polars as pl

from core.domain.models import OptionContract


def list_option_contracts(
    underlying: str, category: str, historical_data_dir: str, expiry: Optional[str] = None,
) -> List[OptionContract]:
    """Every contract ingested for one underlying, optionally narrowed to
    one expiry — same parsing rule backtest_server.py's /api/backtest/
    options/contracts uses (and that endpoint should stay a thin wrapper
    over this, not a second copy of it), reused here by
    chain_sweep_runner.py so a sweep's contract list is computed the exact
    same way the picker's dropdown would show it."""
    underlying_dir = os.path.join(historical_data_dir, "options", category, underlying)
    if not os.path.isdir(underlying_dir):
        return []

    expiries = [expiry] if expiry else sorted(
        d for d in os.listdir(underlying_dir) if os.path.isdir(os.path.join(underlying_dir, d))
    )

    contracts: List[OptionContract] = []
    for exp in expiries:
        expiry_dir = os.path.join(underlying_dir, exp)
        if not os.path.isdir(expiry_dir):
            continue
        expiry_date = dt.date.fromisoformat(exp)
        for fname in sorted(os.listdir(expiry_dir)):
            if not fname.endswith(".csv"):
                continue
            parts = fname[: -len(".csv")].split("_")
            if len(parts) < 3:
                continue
            strike_tok, side_tok = parts[-2], parts[-1]
            try:
                strike = float(strike_tok)
            except ValueError:
                continue
            if side_tok not in ("CE", "PE"):
                continue
            contracts.append(OptionContract(underlying=underlying, strike=strike, expiry=expiry_date, side=side_tok))
    return contracts


def load_lot_sizes(historical_data_dir: str) -> Dict[str, int]:
    """underlying -> lot size, from Data_ingestion/infer_lot_sizes.py's
    output (GCD-of-traded-volume inference, not a hardcoded table -- see
    that module's docstring for why). Missing file or missing underlying
    both just mean "no lot-size check available", handled by callers, not
    here -- this app has no live Kite session guaranteed at backtest time
    to fall back on."""
    path = os.path.join(historical_data_dir, "options", "lot_sizes.csv")
    if not os.path.exists(path):
        return {}
    df = pl.read_csv(path)
    return {
        row["underlying"]: row["inferred_lot_size"]
        for row in df.iter_rows(named=True)
        if row["inferred_lot_size"] is not None
    }


def validate_lot_multiple(underlying: str, quantity: int, lot_sizes: Dict[str, int]) -> Optional[str]:
    """Options can't actually be traded in fractional lots -- a backtest
    configured with a quantity that isn't a whole multiple of the real lot
    size is simulating a position no broker would accept. Returns a
    human-readable warning string if quantity is invalid, None if it's
    fine (including "no lot size on record", since that's a data gap, not
    proof the quantity is wrong) -- a warning rather than a raised
    exception since a batch sweep across many contracts shouldn't abort
    entirely over one misconfigured underlying."""
    lot_size = lot_sizes.get(underlying)
    if not lot_size or quantity % lot_size == 0:
        return None
    nearest = round(quantity / lot_size) * lot_size or lot_size
    return (
        f"{underlying}: quantity {quantity} is not a multiple of its lot size "
        f"{lot_size} (nearest valid quantity: {nearest})"
    )


def option_csv_path(contract: OptionContract, category: str, historical_data_dir: str) -> str:
    """Locates a contract's file under historical_data_dir/options/, matching
    the layout Data_ingestion/options_ingest_stock.py and
    options_ingest_index.py already write: category is "stocks" or "index",
    one folder per underlying, one subfolder per expiry. Takes
    historical_data_dir as a parameter rather than reading settings
    directly, same reasoning as load_equity_csv/load_option_csv taking a
    raw path -- this module doesn't otherwise depend on config."""
    strike_label = f"{contract.strike:g}"
    return os.path.join(
        historical_data_dir,
        "options",
        category,
        contract.underlying,
        contract.expiry.isoformat(),
        f"{contract.underlying}_{strike_label}_{contract.side}.csv",
    )


def load_equity_csv(path: str) -> pl.DataFrame:
    df = pl.read_csv(path, try_parse_dates=True)

    # Kite returns tz-aware IST timestamps; LiveEngine's own candles are
    # naive local time (see live/candle_builder.py) — convert to IST wall
    # clock, then drop the tz label, matching warm_start.py's convention
    # (date.replace(tzinfo=None), not a UTC shift), so a bar's .time()
    # means the same thing whether it came from a live tick or this CSV.
    # polars stores a parsed tz-aware column UTC-normalized internally —
    # replace_time_zone(None) alone would silently expose that UTC value
    # (09:15 IST -> 03:45) instead of the original wall clock, hence the
    # explicit convert_time_zone first.
    if df["date"].dtype != pl.Datetime:
        df = df.with_columns(pl.col("date").str.to_datetime())
    df = df.with_columns(
        pl.col("date").dt.convert_time_zone("Asia/Kolkata").dt.replace_time_zone(None)
    )

    return df.select(
        pl.col("date"),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("volume").cast(pl.Float64),
    ).sort("date")


def load_option_csv(path: str) -> pl.DataFrame:
    """Reads an options_ingest_stock.py / options_ingest_index.py output
    CSV. Unlike load_equity_csv, there's no timezone conversion here -- the
    ingest scripts already store `date` as IST-naive wall clock (see their
    docstrings), so this just parses and sorts. Carries `oi` alongside the
    same open/high/low/close/volume shape load_equity_csv produces, so
    anything already built against that shape keeps working unmodified and
    only code that actually wants OI needs to know it's there.
    """
    df = pl.read_csv(path, try_parse_dates=True)

    return df.select(
        pl.col("date"),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("volume").cast(pl.Float64),
        pl.col("oi").cast(pl.Float64),
    ).sort("date")


def load_backtest_csv(path: str) -> pl.DataFrame:
    """Auto-detects equity vs option shape and dispatches to the loader
    with the right timezone handling -- option CSVs (see
    options_ingest_stock.py/options_ingest_index.py) carry an `oi` column
    equity CSVs never have, and critically already store IST-naive wall
    clock. Running load_equity_csv's UTC->IST conversion on an
    already-naive option file silently shifts every timestamp forward 5.5
    hours (verified: 09:15 becomes 14:45) rather than erroring, so this is
    deliberately the ONE place that dispatch decision gets made -- callers
    (run_backtest.py, parameter_sweep.py) call this instead of either
    loader directly, so they can't each get it wrong independently."""
    header = pl.read_csv(path, n_rows=0).columns
    if "oi" in header:
        return load_option_csv(path)
    return load_equity_csv(path)
