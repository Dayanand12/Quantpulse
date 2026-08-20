"""IMarketDataProvider implemented by wrapping the existing ZerodhaClient.

Data_ingestion/client.py is untouched — this only translates its
`market_data` dict (populated by the tested KiteTicker callback) into
domain Tick objects.
"""

import datetime as dt
import time
from typing import Dict, List, Optional

from core.application.interfaces.market_data_provider import IMarketDataProvider
from core.domain.models import InstrumentRef, Tick
from Data_ingestion.client import ZerodhaClient


class ZerodhaMarketDataProvider(IMarketDataProvider):
    def __init__(self, client: ZerodhaClient, exchange: str) -> None:
        self._client = client
        self._exchange = exchange

    def start(self, symbols: List[str]) -> None:
        self._client.start_live_data(symbols, self._exchange)

    def add_symbol(self, symbol: str) -> None:
        self._client.add_symbol(symbol, self._exchange)

    def seconds_since_last_tick(self) -> Optional[float]:
        if self._client.last_tick_at is None:
            return None
        return time.time() - self._client.last_tick_at

    def get_latest_ticks(self) -> Dict[str, Tick]:
        now = dt.datetime.now()
        return {
            symbol: Tick(
                symbol=symbol,
                ltp=data["LTP"],
                volume=data.get("Volume", 0),
                timestamp=now,
                prev_close=data.get("C"),
            )
            for symbol, data in self._client.market_data.items()
            if "LTP" in data
        }

    def find_instrument(self, symbol: str) -> Optional[InstrumentRef]:
        info = self._client.find_instrument(symbol, self._exchange)
        if info is None:
            return None
        return InstrumentRef(instrument_token=info["instrument_token"], exchange=info["exchange"])
