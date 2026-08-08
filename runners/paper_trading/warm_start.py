# live/warm_start.py
"""Backfills LiveEngine with already-elapsed candles at startup, via
Data_ingestion/client.py::ZerodhaClient.fetch_historical_data — the same
1-minute historical API MarketAnalysisEngine uses.

Without this, every restart starts every symbol from zero candles:
indicators need ~25 one-minute candles before they produce a value (see
live/live_engine.py's `if df.height < 25: return`), and orb_reversal's
opening range is captured ONLY while candles pass through the live
9:15-9:30 window — a restart after 9:30 permanently loses today's
opening range for that symbol, not just delays it. Replaying today's
(plus a little of the prior session, for EMA21/ADX14 warm-up) historical
candles through the exact same on_new_candle() path fixes both.

One symbol failing (no data yet, a rate limit, a network blip) must never
block the others or crash startup — caught and logged per symbol.
"""

import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

# Calendar days of 1-minute history to fetch per symbol. Needs to cover
# the SLOWEST supported timeframe's warm-up, not just 1-minute: a
# deployment on live/live_engine.py's 30-minute timeframe needs 25 bars
# of 30 minutes each (~750 minutes, ~2 trading days) before it produces a
# value at all. 10 calendar days comfortably covers that plus weekends/
# holidays, matching backend/market_analysis_engine.py's own lookback.
_LOOKBACK_DAYS = 10

# fetch_historical_data() is one network round-trip per symbol; run them
# concurrently instead of one-at-a-time (this used to block app startup
# for the full sum of 53+ sequential round-trips). Capped at 3 — Kite's
# historical-data endpoint is rate-limited to ~3 req/s, and going wider
# just trades this delay for 429s.
_MAX_CONCURRENT_FETCHES = 3


def _fetch_and_warm_start(live_engine, zerodha_client, symbol, exchange, from_date, now) -> None:
    try:
        candles = zerodha_client.fetch_historical_data(
            symbol=symbol,
            interval="minute",
            from_date=from_date,
            to_date=now,
            exchange=exchange,
        )
        if not candles:
            return

        live_engine.warm_start(symbol, candles)
        logger.info("Warm-started %s with %d historical candles", symbol, len(candles))
    except Exception:
        logger.exception("Warm-start: failed to fetch/replay history for %s", symbol)


def warm_start_indicators(live_engine, zerodha_client, symbols, exchange) -> None:
    now = dt.datetime.now()
    from_date = now - dt.timedelta(days=_LOOKBACK_DAYS)

    with ThreadPoolExecutor(max_workers=_MAX_CONCURRENT_FETCHES) as pool:
        futures = [
            pool.submit(_fetch_and_warm_start, live_engine, zerodha_client, symbol, exchange, from_date, now)
            for symbol in symbols
        ]
        for future in as_completed(futures):
            future.result()
