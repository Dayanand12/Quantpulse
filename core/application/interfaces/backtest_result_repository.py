"""Port: durable storage for backtest results — the "automatic logging
instead of an Excel sheet" the Analysis tab reads from. See
core/domain/backtest_result.py for the identity/dedup rules.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.domain.backtest_result import BacktestResult, BacktestRunParams


class IBacktestResultRepository(ABC):
    @abstractmethod
    def save_result(self, params: BacktestRunParams, result: Dict[str, Any]) -> BacktestResult:
        """Insert a new row, or update the existing one in place if a row
        with identical `params` already exists — never creates a
        duplicate for the same inputs."""

    @abstractmethod
    def list_results(self, strategy_name: str) -> List[BacktestResult]:
        """Every stored run for one strategy, most recently updated
        first — feeds the Analysis tab's parameter-combination dropdown
        and comparison chart."""

    @abstractmethod
    def get_result(self, result_id: int) -> Optional[BacktestResult]:
        """One stored run's full result, or None if it doesn't exist."""

    @abstractmethod
    def delete_result(self, result_id: int) -> None:
        """Removes one stored run. A no-op if it doesn't exist — deleting
        something already gone isn't an error."""

    @abstractmethod
    def list_option_results(self, strategy_name: str, underlying: Optional[str] = None) -> List[BacktestResult]:
        """Every stored OPTION run for one strategy (option_underlying IS
        NOT NULL — see models.py::BacktestResultRecord), optionally
        narrowed to one underlying. Feeds the Options Analysis tab — a
        strategy swept across a full option chain can have thousands of
        rows, so this filters in SQL rather than the caller fetching
        list_results() and filtering client-side."""

    @abstractmethod
    def list_option_underlyings(self, strategy_name: str) -> List[str]:
        """Distinct underlyings this strategy has ANY stored option result
        for, alphabetical — populates the Options Analysis tab's
        Underlying filter without fetching every row first."""
