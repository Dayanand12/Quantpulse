"""Port: a strategy's tunable parameters/conditions (core/domain/
strategy_conditions.py) — the JSON file sitting next to a strategy's .py,
editable from the Backtest screen without touching code. Not every
strategy has one yet (only those migrated off hand-written screen()
logic), so get_params() returns None rather than raising for those.
"""

from abc import ABC, abstractmethod
from typing import Optional


class IStrategyParamsRepository(ABC):
    @abstractmethod
    def get_params(self, name: str) -> Optional[str]:
        """Raw JSON text for strategy `name`, or None if it has no params
        file."""

    @abstractmethod
    def save_params(self, name: str, raw_json: str) -> None:
        """Overwrites an existing params file after validating it parses
        as a well-formed condition set. Raises NotFoundError if the
        strategy has no params file yet (use create_params for that)."""

    @abstractmethod
    def create_params(self, name: str, raw_json: str) -> None:
        """Writes a new params file — used when cloning a strategy that
        has one. Raises ValidationError if one already exists."""

    @abstractmethod
    def delete_params(self, name: str) -> None:
        """Deletes a params file if one exists. A no-op (not an error) if
        the strategy never had one — deleting a strategy that hasn't been
        migrated to condition-JSON is still a valid delete."""
