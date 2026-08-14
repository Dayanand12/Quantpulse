"""Port: durable storage for chain sweeps (core/domain/chain_sweep.py) —
lets a background-processed option-chain sweep survive a browser close, a
page reload, or checking back tomorrow. Mirrors IBatchJobRepository's
shape exactly; see that interface's docstring for the reasoning.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from core.domain.chain_sweep import ChainSweep


class IChainSweepRepository(ABC):
    @abstractmethod
    def create(self, sweep: ChainSweep) -> ChainSweep:
        """Inserts a new sweep (status="pending", contracts already
        populated as "pending") and returns it with its assigned id."""

    @abstractmethod
    def save(self, sweep: ChainSweep) -> ChainSweep:
        """Overwrites an existing sweep's mutable state (status, each
        contract's status/result/error, finished_at) — the background
        runner calls this after every contract (or small chunk) so
        progress is always durable, never only in the runner's memory."""

    @abstractmethod
    def get(self, sweep_id: int) -> Optional[ChainSweep]:
        """One sweep's full current state, or None if it doesn't exist."""

    @abstractmethod
    def list_for_strategy(self, strategy_name: str, limit: int = 20) -> List[ChainSweep]:
        """Most recent sweeps for a strategy, newest first."""
