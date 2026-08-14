"""Port: named, user-organized groups of symbols the app tracks/trades.

Today's adapter is SQL-backed (infrastructure/persistence). Every
watchlist's symbols are streamed/warmed together (see get_all_symbols) —
watchlists are an organizing concept for how a human browses/picks
symbols, not a routing concept for what the live engine subscribes to.
run_live.py seeds a "Default" watchlist once from the legacy
Data_ingestion/stocks.json the first time no watchlist exists.
"""

from abc import ABC, abstractmethod
from typing import List

from core.domain.models import Watchlist


class IWatchlistRepository(ABC):
    @abstractmethod
    def list_watchlists(self) -> List[Watchlist]:
        """Every watchlist, each with its own symbols, in creation order."""

    @abstractmethod
    def create_watchlist(self, name: str) -> Watchlist:
        """A new, empty watchlist. Raises ValueError if the name is already taken."""

    @abstractmethod
    def rename_watchlist(self, watchlist_id: int, name: str) -> Watchlist:
        """Raises ValueError if watchlist_id doesn't exist or name is taken."""

    @abstractmethod
    def delete_watchlist(self, watchlist_id: int) -> None:
        """Raises ValueError if this is the only remaining watchlist —
        the app always needs at least one to seed the live engine from."""

    @abstractmethod
    def get_symbols(self, watchlist_id: int) -> List[str]:
        """Symbols in one watchlist, in save order."""

    @abstractmethod
    def save_symbols(self, watchlist_id: int, symbols: List[str]) -> Watchlist:
        """Replace one watchlist's symbols. Callers should not assume this
        affects a currently running engine — symbols apply on next restart."""

    @abstractmethod
    def get_all_symbols(self) -> List[str]:
        """Deduplicated union of every watchlist's symbols — what the live
        engine/websocket/backtesting actually subscribe to and validate
        deployments against."""
