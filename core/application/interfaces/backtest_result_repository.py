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
