# core/domain/chain_sweep.py
"""A chain sweep — one strategy + one risk/sizing config, run automatically
against every option contract (every strike x every side, optionally
narrowed to one expiry) for a single underlying, so answering "does this
strategy work on options at all" doesn't require hand-picking one
contract at a time through OptionContractPicker (see frontend/src/
components/backtest/OptionContractPicker.tsx).

Structurally the options counterpart to core/domain/batch_job.py's
BatchJob, and deliberately NOT a reuse of that class: BatchJob varies
STRATEGY PARAMETERS across scenarios while holding one fixed symbol set
constant for the whole job ("symbols are the one thing that stays
job-level" — see batch_job.py's docstring) -- a chain sweep is the
opposite shape, one fixed strategy config varying across MANY symbols
(contracts). Forcing that into BatchJob's scenario model would fight its
documented invariant rather than reuse it cleanly.

Runs in the background (runners/backtesting/chain_sweep_runner.py) for
the same reason BatchJob does: a single underlying's full chain across
every expiry can be hundreds to low thousands of contracts -- comfortably
past what a synchronous request should hold open.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

CONTRACT_STATUSES = ("pending", "running", "done", "skipped", "error")
SWEEP_STATUSES = ("pending", "running", "done", "failed")


@dataclass
class ChainSweepContract:
    """One contract's progress + a denormalized slice of its result
    (win_rate/profit_factor/total_pnl/total_trades) so the ranked-results
    view can sort/filter without an N+1 fetch back to backtest_results per
    contract -- same reasoning as BacktestResultSummary on the frontend
    flattening a stored result's key metrics for the Analysis dropdown."""

    symbol: str  # OptionContract.symbol string, e.g. "RELIANCE:1600CE:2026-01-27"
    status: str = "pending"
    saved_result_id: Optional[int] = None
    error: Optional[str] = None
    total_trades: Optional[int] = None
    total_pnl: Optional[float] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None


@dataclass
class ChainSweep:
    """`shared_config` is the one risk/sizing config applied to every
    contract — same shape as BatchJob.shared_config minus `symbols` (a
    sweep's contract list IS its symbol set, computed from
    underlying/category/expiry_filter, not supplied directly)."""

    strategy_name: str
    underlying: str
    category: str  # "stocks" | "index"
    shared_config: Dict[str, Any]
    contracts: List[ChainSweepContract] = field(default_factory=list)
    # None -> every expiry this underlying has ingested data for.
    expiry_filter: Optional[str] = None
    status: str = "pending"
    id: Optional[int] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @property
    def total_contracts(self) -> int:
        return len(self.contracts)

    @property
    def processed_contracts(self) -> int:
        return sum(1 for c in self.contracts if c.status in ("done", "skipped", "error"))
