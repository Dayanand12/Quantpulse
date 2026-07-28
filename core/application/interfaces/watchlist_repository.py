"""Port: the set of symbols the app tracks/trades.

Today's adapter is SQL-backed (infrastructure/persistence). Reading returns
whatever was last saved; run_live.py seeds it once from the legacy
Data_ingestion/stocks.json the first time the table is empty.
"""

from abc import ABC, abstractmethod
from typing import List


class IWatchlistRepository(ABC):
    @abstractmethod
    def get_symbols(self) -> List[str]:
        """Return the currently configured watchlist, in save order."""

    @abstractmethod
    def save_symbols(self, symbols: List[str]) -> None:
        """Replace the watchlist. Callers should not assume this affects a
        currently running engine — symbols apply on next restart."""
