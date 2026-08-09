# runners/backtesting/snapshot_builder.py
"""Vectorized equivalent of LiveEngine._update_snapshot (runners/paper_trading/
live_engine.py) — same indicator set, same snapshot dict shape (so IStrategy
implementations run unmodified against it), but computed once over the
WHOLE historical series instead of recomputed from scratch on every new
candle. LiveEngine's recompute-per-candle is fine live (one candle a
minute); replaying years of history through that same path is O(n^2) and
was measured to take minutes for a single symbol's 10-day warm-start once
multi-timeframe support was added (see live_engine.py's warm_start
docstring) — this module is what avoids paying that cost per backtest run.

Reuses LiveEngine._resample directly (a pure function of df + minutes, no
live state) so timeframe bucketing is guaranteed identical to live.
"""

import datetime as dt
from typing import List, Optional

import polars as pl

from core.domain.indicator_registry import IndicatorSpec
from core.domain.indicator_registry import compute_all as compute_dynamic_indicators
from indicators import IndicatorCalculator
from runners.paper_trading.live_engine import LiveEngine

# Opening range window LiveEngine tracks (see live_engine.py::_ingest_candle)
# — always off the 1-minute base series, independent of the strategy's
# chosen timeframe.
_OR_START = dt.time(9, 15)
_OR_END = dt.time(9, 30)

# Bars needed before an indicator/snapshot is considered valid — matches
# live_engine.py::_update_snapshot's `if df.height < 25: return`.
_MIN_BARS = 25

_VOLUME_RATIO_WINDOW = 20


def _opening_range(base_df: pl.DataFrame) -> pl.DataFrame:
    """One row per session date: that day's OR low/high (min low / max
    high, 9:15-9:30 on the 1-minute base). Distance-to-OR-low and orb_high
    are only meaningful once the OR window itself has fully elapsed
    (matches live_engine.py's `locked` flag, which flips true only after a
    candle later than 9:30 arrives) — masked to None before that in
    build_snapshot_series below, so a strategy can never "see" the
    session's final OR high/low before it's actually finished forming
    (this whole aggregate is computed as one batch over the full 9:15-9:30
    window per day, so without that masking a bar from e.g. 9:20 would
    otherwise leak the 9:30 OR value — impossible live, where it's only
    known incrementally as candles actually arrive)."""
    or_window = base_df.filter(
        (pl.col("date").dt.time() >= _OR_START) & (pl.col("date").dt.time() <= _OR_END)
    )
    return (
        or_window.group_by(pl.col("date").dt.date().alias("session_date"))
        .agg(pl.col("low").min().alias("orb_low"), pl.col("high").max().alias("orb_high"))
    )


def build_snapshot_series(
    base_df: pl.DataFrame,
    timeframe_minutes: int,
    extra_indicators: Optional[List[IndicatorSpec]] = None,
) -> pl.DataFrame:
    """base_df: 1-minute OHLCV (see historical_loader.load_equity_csv).
    Returns one row per bar at `timeframe_minutes` resolution, columns
    matching LiveEngine.get_snapshot()'s per-symbol dict exactly: date,
    ltp, ema5, ema9, ema21, rsi, adx, atr_pct, vwap, volume_ratio, orb_low,
    distance_to_or_low. Rows before _MIN_BARS warm-up are dropped, same as
    live (a strategy never sees a snapshot for those).

    extra_indicators: any additional dynamically-requested indicators
    (core/domain/indicator_registry.py — e.g. a strategy's
    conditions.json asking for {"indicator": "ema", "params": {"period":
    20}}), computed alongside the always-available set above and added
    as extra columns keyed by their canonical name (e.g. "ema_20"). Never
    changes the fixed set's own values — purely additive."""
    extra_indicators = extra_indicators or []
    extra_keys = [spec.key for spec in extra_indicators]

    or_by_day = _opening_range(base_df)

    tf_df = base_df if timeframe_minutes == 1 else LiveEngine._resample(base_df, timeframe_minutes)
    if tf_df.height < _MIN_BARS:
        return tf_df.clear().with_columns(
            pl.lit(None, dtype=pl.Float64).alias(c)
            for c in ("ltp", "ema5", "ema9", "ema21", "rsi", "adx", "atr_pct", "vwap",
                      "volume_ratio", "orb_low", "orb_high", "distance_to_or_low", *extra_keys)
        )

    ema5 = IndicatorCalculator.ema(tf_df, period=5)
    ema9 = IndicatorCalculator.ema(tf_df, period=9)
    ema21 = IndicatorCalculator.ema(tf_df, period=21)
    rsi14 = IndicatorCalculator.rsi(tf_df, period=14)
    adx14 = IndicatorCalculator.adx(tf_df, period=14)
    atr14 = IndicatorCalculator.atr(tf_df, period=14)

    out = tf_df.with_columns([ema5, ema9, ema21, rsi14, adx14, atr14])
    out = out.with_columns((pl.col("ATR_14") / pl.col("close") * 100).alias("atr_pct"))

    # Dynamic indicators computed on the SAME tf_df (still has close/high/
    # low under their original OHLC names, same as every fixed indicator
    # above needs) — before the close->ltp rename below.
    out = compute_dynamic_indicators(extra_indicators, out)

    out = out.with_columns(pl.col("date").dt.date().alias("session_date"))

    # Cumulative intraday VWAP — the running "day so far" average LiveEngine
    # recomputes on every candle; here as a single windowed cumsum per
    # session date instead of one recompute per row.
    out = out.with_columns(
        (
            (pl.col("close") * pl.col("volume")).cum_sum().over("session_date")
            / pl.col("volume").cum_sum().over("session_date")
        ).alias("vwap")
    )

    # Rolling mean of the trailing 20 bars INCLUDING the current one —
    # matches live_engine.py's `df["volume"][-20:].mean()`.
    out = out.with_columns(
        pl.col("volume").rolling_mean(window_size=_VOLUME_RATIO_WINDOW, min_samples=1).alias("_avg_vol")
    )
    out = out.with_columns(
        pl.when(pl.col("_avg_vol") > 0)
        .then(pl.col("volume") / pl.col("_avg_vol"))
        .otherwise(0.0)
        .alias("volume_ratio")
    )

    out = out.join(or_by_day, on="session_date", how="left")
    out = out.with_columns(
        pl.when(pl.col("date").dt.time() > _OR_END)
        .then((pl.col("close") - pl.col("orb_low")) / pl.col("orb_low") * 100)
        .otherwise(None)
        .alias("distance_to_or_low")
    )
    # orb_high masked the same way — see _opening_range's docstring for
    # why this can't just be the raw joined value.
    out = out.with_columns(
        pl.when(pl.col("date").dt.time() > _OR_END)
        .then(pl.col("orb_high"))
        .otherwise(None)
        .alias("orb_high")
    )

    out = out.rename({
        "close": "ltp",
        "EMA_5": "ema5",
        "EMA_9": "ema9",
        "EMA_21": "ema21",
        "RSI_14": "rsi",
        "ADX_14": "adx",
    })

    # high/low ride along for the engine's own SL/target touch checks
    # (a bar can swing through a level without its close reflecting it —
    # see runners/backtesting/engine.py) but are deliberately NOT part of
    # LiveEngine.get_snapshot()'s shape, so they must never be forwarded
    # into IStrategy.screen()'s snapshot dict.
    return out.select(
        "date", "ltp", "high", "low", "ema5", "ema9", "ema21", "rsi", "adx", "atr_pct",
        "vwap", "volume_ratio", "orb_low", "orb_high", "distance_to_or_low", *extra_keys,
    ).tail(out.height - _MIN_BARS + 1)
