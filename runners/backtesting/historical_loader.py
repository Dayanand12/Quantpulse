# runners/backtesting/historical_loader.py
"""Reads a Data_ingestion-style equity OHLCV CSV (date,open,high,low,close,
volume — see Data_ingestion/run_client.py::fetch_historical) into the same
schema LiveEngine keeps in `self.data[symbol]`, so every downstream piece
(resampling, indicator calc) works unmodified on either live or historical
candles.
"""

import polars as pl


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
