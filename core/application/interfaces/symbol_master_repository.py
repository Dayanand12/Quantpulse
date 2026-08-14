"""Port: NSE equity symbol master, for typeahead suggestions while typing
a symbol into a watchlist. This is a suggestion source, not a tradeable-
status source of truth — Kite's instrument dump / the watchlist itself
still govern what's actually tracked and tradeable.
"""

from abc import ABC, abstractmethod
from typing import List, NamedTuple


class SymbolSuggestion(NamedTuple):
    tradingsymbol: str
    name: str


class ISymbolMasterRepository(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 20) -> List[SymbolSuggestion]:
        """Symbols whose tradingsymbol or company name contains query
        (case-insensitive), tradingsymbol matches ranked first."""

    @abstractmethod
    def replace_all(self, symbols: List[SymbolSuggestion]) -> None:
        """Full resync from Kite's instrument dump — replaces every row."""

    @abstractmethod
    def count(self) -> int:
        """How many symbols are currently stored — lets the UI show
        whether a resync has ever been run."""
