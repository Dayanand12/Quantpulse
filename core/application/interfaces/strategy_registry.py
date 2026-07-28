"""Port: discovery/lookup of available strategies.

Default adapter scans a strategies/ folder and imports whatever it finds
(infrastructure/strategies/file_strategy_registry.py) — dropping a new
.py file there is how a new strategy becomes deployable, no code changes
elsewhere.
"""

from abc import ABC, abstractmethod
from typing import List

from core.application.interfaces.strategy import IStrategy


class IStrategyRegistry(ABC):
    @abstractmethod
    def list_strategies(self) -> List[IStrategy]:
        """Return every discovered strategy."""

    @abstractmethod
    def get_strategy(self, name: str) -> IStrategy:
        """Look up a strategy by its unique name. Raises NotFoundError if unknown."""
