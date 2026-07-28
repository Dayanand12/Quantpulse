import polars as pl
import datetime as dt
from backtest.indicators import IndicatorCalculator
from live.paper_broker import PaperBroker
from live.candle_builder import CandleBuilder


class LiveEngine:

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

        self.indicator_snapshot = {}

        # OR tracking per symbol
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
    # Candle closed → compute indicators
    # -----------------------------------
    def on_new_candle(self, symbol, candle):

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
        # Append Candle
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
        df = self.data[symbol]

        # -----------------------
        # OR LOGIC (9:15–9:30)
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

        # Need enough candles
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
        self.indicator_snapshot[symbol] = {
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

    def get_snapshot(self):
        return self.indicator_snapshot

    def status(self):
        return self.broker.status()