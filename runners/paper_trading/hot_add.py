# runners/paper_trading/hot_add.py
"""Adds a single symbol to an already-running live engine — no process
restart needed. Used when a watchlist save introduces a symbol nothing
has tracked yet (server/main.py's watchlist-symbols endpoint).

Order matters and is deliberately NOT parallel with anything else for
this one symbol:
  1. LiveEngine.add_symbol() — seeds empty data/or_data/indicator_snapshot
     slots, synchronously, before anything else can touch this symbol.
  2. Historical backfill (warm_start) — safe now that slots exist; still
     no live ticks are flowing for this symbol yet, so there's no
     concurrent writer racing the backfill's own candle-by-candle inserts.
  3. Subscribe on the live feed (ONLY after backfill finishes) — from this
     point on, ticks for this symbol start arriving and get processed
     through the normal tick_loop path.

Doing it in any other order risks a tick arriving before step 1 (KeyError
in LiveEngine._ingest_candle) or racing step 2's writes (step 3 before 2).
"""

import datetime as dt

from core.application.interfaces.market_data_provider import IMarketDataProvider
from Data_ingestion.client import ZerodhaClient
from infrastructure.logging.logger import get_logger
from runners.paper_trading.live_engine import LiveEngine
from runners.paper_trading.warm_start import _LOOKBACK_DAYS, fetch_and_warm_start

logger = get_logger(__name__)


def hot_add_symbol(
    live_engine: LiveEngine,
    zerodha_client: ZerodhaClient,
    market_data_provider: IMarketDataProvider,
    symbol: str,
) -> None:
    if symbol in live_engine.data:
        return  # already tracked — nothing to do

    live_engine.add_symbol(symbol)

    now = dt.datetime.now()
    from_date = now - dt.timedelta(days=_LOOKBACK_DAYS)
    fetch_and_warm_start(live_engine, zerodha_client, symbol, zerodha_client.exchange, from_date, now)

    market_data_provider.add_symbol(symbol)
    logger.info("Hot-added %s to the live feed (no restart)", symbol)
