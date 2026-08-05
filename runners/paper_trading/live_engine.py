import polars as pl
import datetime as dt
from indicators import IndicatorCalculator
from runners.paper_trading.paper_broker import PaperBroker
from runners.paper_trading.candle_builder import CandleBuilder

# Every timeframe a deployment can be configured for (core/domain/models.py
# ::StrategyConfig.timeframe) — Kite's own interval-string vocabulary, for
# familiarity, though these are never passed to Kite directly (see
# live/warm_start.py: the historical fetch always stays at "minute"
# resolution; every other timeframe here is derived from it by resampling,
# not fetched separately). Value = bar width in minutes.
SUPPORTED_TIMEFRAMES = {
    "minute": 1,
    "3minute": 3,
    "5minute": 5,
    "10minute": 10,
    "15minute": 15,
    "30minute": 30,
}


class LiveEngine:

    # NSE cash session open — every resampled timeframe's bar boundaries
    # are anchored here, not midnight. Intervals that don't evenly divide
    # 60 (3, 10) would otherwise misalign with the wall-clock candles a
    # trader actually sees on their broker's chart if bucketed from
    # midnight instead (see docs/plans/per-strategy-timeframes.md).
    _SESSION_OPEN_MINUTES = 9 * 60 + 15  # 09:15

    def __init__(self, symbols, capital=100000):
        self.symbols = symbols
        self.broker = PaperBroker(capital)
        self.builder = CandleBuilder(symbols)

        self.data = {
            symbol: pl.DataFrame(
                schema={
                    "date": pl.Datetime,
                    "open": pl.Float64,
                    "high": pl.Float64,
                    "low": pl.Float64,
                    "close": pl.Float64,
                    "volume": pl.Float64
                }
            )
            for symbol in symbols
        }

        # symbol -> timeframe -> {ltp, ema5, ..., orb_low, distance_to_or_low}
        self.indicator_snapshot = {}

        # OR tracking per symbol — wall-clock (9:15-9:30), independent of
        # any strategy's chosen timeframe.
        self.or_data = {
            symbol: {
                "high": None,
                "low": None,
                "locked": False,
                "date": None
            }
            for symbol in symbols
        }

    # -----------------------------------
    # Called from tick loop
    # -----------------------------------
    def process_tick(self, symbol, tick):

        candle = self.builder.update_tick(symbol, tick)

        if candle:
            self.on_new_candle(symbol, candle)

    # -----------------------------------
    # Startup warm-start (see live/warm_start.py) — replays already-
    # elapsed candles (e.g. from Kite's historical API) so indicators and
    # today's opening range are ready immediately instead of only after
    # ~25 live ticks / never (if today's 9:15-9:30 OR window has already
    # passed by the time this process started).
    #
    # Deliberately does NOT call on_new_candle() per historical candle —
    # that would resample the whole (growing) series across every
    # supported timeframe once per candle, i.e. O(n) resamples of O(n)
    # data = O(n^2) for a single symbol's warm-start (measured: this made
    # a ~3,000-candle/10-day backfill take minutes instead of seconds
    # once multi-timeframe support was added). Every intermediate
    # snapshot during replay is immediately superseded and never read by
    # anyone, so it's safe to only ingest (append + OR tracking) per
    # candle and recompute indicators once, after the full batch —
    # identical end state, far less redundant work.
    # -----------------------------------
    def warm_start(self, symbol, historical_candles):
        for candle in historical_candles:
            date = candle["date"]
            if date.tzinfo is not None:
                # Kite returns tz-aware IST timestamps; every other candle
                # here is naive local time (see live/candle_builder.py) —
                # strip tzinfo without shifting the wall-clock value,
                # since it's already IST, not converting between zones.
                date = date.replace(tzinfo=None)
            self._ingest_candle(symbol, {**candle, "date": date})

        self._recompute_all_timeframes(symbol)

    # -----------------------------------
    # Resample the 1-minute base series into `minutes`-wide bars, anchored
    # to the session open. The last bucket is a partial, still-forming bar
    # by design — indicators should update continuously as it fills in,
    # the same way a live trading chart's current candle does, not sit
    # stale until a full bar's worth of time has elapsed.
    # -----------------------------------
    @classmethod
    def _resample(cls, df: pl.DataFrame, minutes: int) -> pl.DataFrame:
        if minutes == 1:
            return df

        minutes_since_midnight = (
            pl.col("date").dt.hour().cast(pl.Int64) * 60
            + pl.col("date").dt.minute().cast(pl.Int64)
        )
        minutes_since_open = minutes_since_midnight - cls._SESSION_OPEN_MINUTES
        bucket_index = minutes_since_open // minutes
        bucket_offset = (bucket_index * minutes + cls._SESSION_OPEN_MINUTES).cast(pl.Int64)
        bucket_start = pl.col("date").dt.truncate("1d") + pl.duration(minutes=bucket_offset)

        return (
            df.with_columns(bucket_start.alias("bucket"))
            .group_by("bucket", maintain_order=True)
            .agg([
                pl.col("open").first(),
                pl.col("high").max(),
                pl.col("low").min(),
                pl.col("close").last(),
                pl.col("volume").sum(),
            ])
            .rename({"bucket": "date"})
            .sort("date")
        )

    # -----------------------------------
    # Candle closed → ingest it, then recompute every supported
    # timeframe's indicators. Used by the live tick path (one new candle
    # at a time, so the O(n) resample-and-recompute cost below is trivial
    # — it's at most a few hundred rows, once a minute). Warm-start
    # (above) uses _ingest_candle directly instead, to avoid paying this
    # cost once per historical candle.
    # -----------------------------------
    def on_new_candle(self, symbol, candle):
        self._ingest_candle(symbol, candle)
        self._recompute_all_timeframes(symbol)

    def _ingest_candle(self, symbol, candle):
        candle_date = candle["date"].date()

        # -----------------------
        # DAILY OR RESET
        # -----------------------
        if self.or_data[symbol]["date"] != candle_date:
            self.or_data[symbol] = {
                "high": None,
                "low": None,
                "locked": False,
                "date": candle_date
            }

        # -----------------------
        # Append Candle (1-minute base — single source of truth every
        # timeframe is derived from)
        # -----------------------
        new_row = pl.DataFrame([{
            "date": candle["date"],
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": float(candle["volume"]),
        }])

        self.data[symbol] = pl.concat([self.data[symbol], new_row])

        # -----------------------
        # OR LOGIC (9:15–9:30) — off the raw 1-minute candles, independent
        # of any resampled timeframe
        # -----------------------
        candle_time = candle["date"].time()

        if not self.or_data[symbol]["locked"]:

            if dt.time(9, 15) <= candle_time <= dt.time(9, 30):

                if self.or_data[symbol]["high"] is None:
                    self.or_data[symbol]["high"] = candle["high"]
                    self.or_data[symbol]["low"] = candle["low"]
                else:
                    self.or_data[symbol]["high"] = max(
                        self.or_data[symbol]["high"], candle["high"]
                    )
                    self.or_data[symbol]["low"] = min(
                        self.or_data[symbol]["low"], candle["low"]
                    )

            if candle_time > dt.time(9, 30):
                self.or_data[symbol]["locked"] = True

    def _recompute_all_timeframes(self, symbol):
        base_df = self.data[symbol]
        self.indicator_snapshot.setdefault(symbol, {})

        for timeframe, minutes in SUPPORTED_TIMEFRAMES.items():
            tf_df = base_df if minutes == 1 else self._resample(base_df, minutes)
            self._update_snapshot(symbol, timeframe, tf_df)

    def _update_snapshot(self, symbol, timeframe, df):
        # Need enough bars at THIS timeframe specifically — a higher
        # timeframe reaches 25 bars later than the 1-minute base does.
        if df.height < 25:
            return

        # -----------------------
        # Compute Indicators
        # -----------------------
        ema5 = IndicatorCalculator.ema(df, period=5)
        ema9 = IndicatorCalculator.ema(df, period=9)
        ema21 = IndicatorCalculator.ema(df, period=21)
        rsi14 = IndicatorCalculator.rsi(df, period=14)
        adx14 = IndicatorCalculator.adx(df, period=14)
        atr14 = IndicatorCalculator.atr(df, period=14)

        df = df.with_columns([ema5, ema9, ema21, rsi14, adx14, atr14])
        latest = df.row(-1, named=True)

        # -----------------------
        # TRUE SESSION VWAP
        # -----------------------
        today = dt.date.today()
        session_df = df.filter(pl.col("date").dt.date() == today)

        if session_df.height == 0:
            return

        total_volume = session_df["volume"].sum()

        if total_volume == 0:
            return

        vwap = (session_df["close"] * session_df["volume"]).sum() / total_volume

        # -----------------------
        # Volume Ratio
        # -----------------------
        last_vol = df["volume"][-1]
        avg_vol = df["volume"][-20:].mean()
        volume_ratio = float(last_vol / avg_vol) if avg_vol > 0 else 0

        # ATR %
        atr_pct = (latest["ATR_14"] / latest["close"]) * 100

        # OR Distance
        orb_low = self.or_data[symbol]["low"]
        distance_to_or_low = None

        if (
            orb_low is not None and
            self.or_data[symbol]["locked"]
        ):
            distance_to_or_low = (
                (latest["close"] - orb_low) / orb_low
            ) * 100

        # -----------------------
        # Save Snapshot
        # -----------------------
        self.indicator_snapshot[symbol][timeframe] = {
            "ltp": float(latest["close"]),
            "ema5": float(latest["EMA_5"]),
            "ema9": float(latest["EMA_9"]),
            "ema21": float(latest["EMA_21"]),
            "rsi": float(latest["RSI_14"]),
            "adx": float(latest["ADX_14"]),
            "atr_pct": float(atr_pct),
            "vwap": float(vwap),
            "volume_ratio": float(volume_ratio),
            "orb_low": float(orb_low) if orb_low else None,
            "distance_to_or_low": float(distance_to_or_low) if distance_to_or_low else None
        }

    def get_snapshot(self, timeframe="minute"):
        return {
            symbol: tf_snapshots[timeframe]
            for symbol, tf_snapshots in self.indicator_snapshot.items()
            if timeframe in tf_snapshots
        }

    def status(self):
        return self.broker.status()
