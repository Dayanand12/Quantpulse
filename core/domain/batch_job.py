# core/domain/batch_job.py
"""A batch job — one uploaded Excel of parameter scenarios for a single
strategy, processed in the background (runners/backtesting/
batch_job_runner.py) so closing the browser (or the laptop) mid-run
doesn't lose anything: each scenario is saved to backtest_results as soon
as IT finishes, not all at the end, and this row's own status updates in
place as processing goes — see infrastructure/persistence/
sql_batch_job_repository.py.

Distinct from the "6 panels" feature (runners/backtesting/batch_runner.py,
POST /api/backtest/run-batch): that one is synchronous and capped at 6,
built for "try a few variants right now and watch them come in." This one
is for "I prepared 50 scenarios offline, run them all and I'll check back
later" — no cap, detached from the HTTP request that started it.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# A scenario's lifecycle: "pending" (queued, not yet started) ->
# "running" (currently being backtested) -> "done" (freshly computed and
# saved). "skipped" is the other successful terminal state: reached
# straight from "pending" when an identical result (same strategy,
# symbols, dates, risk/sizing, and resolved parameters) already exists in
# backtest_results — see runners/backtesting/batch_job_runner.py's
# pre-run dedup check, which exists so re-uploading "my last export plus a
# few new rows" only spends time on the genuinely new ones. "invalid" is a
# dead end reached straight from parsing the upload (a typo'd parameter
# name, a non-numeric value) — never runs at all. "error" is reached from
# "running" if the backtest itself blew up (e.g. every requested symbol
# turned out to have no historical data) — same "skip it, keep going"
# treatment as "invalid", just discovered later.
SCENARIO_STATUSES = ("pending", "running", "done", "skipped", "invalid", "error")
JOB_STATUSES = ("pending", "running", "done", "failed")


@dataclass
class BatchJobScenario:
    """`overrides` is this scenario's strategy-parameter values (e.g.
    adx_threshold) — always present, that's the whole point of a scenario.
    `config_overrides` is what this ROW specifically set for the
    risk/sizing fields (stoploss_pct, timeframe, quantity, ...) that
    otherwise come from the job's shared_config — a PARTIAL dict, only the
    fields this row actually specified; anything absent falls back to
    shared_config at run time (see runners/backtesting/batch_job_runner.py
    ::_resolve_scenario_config). A blank Stop Loss % cell means "use the
    job's shared setting," not "zero.\""""

    label: str
    overrides: Dict[str, float]
    config_overrides: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    saved_result_id: Optional[int] = None
    error: Optional[str] = None


@dataclass
class BatchJob:
    """`shared_config` is the run settings every scenario in this job uses
    (symbols, dates, timeframe, risk/sizing) — same shape as a single
    run's config minus strategy/panels, see backtest_server.py's
    BatchJobUploadRequest. `status` is the JOB's overall state: "failed"
    means an unexpected exception killed background processing entirely
    (not just one scenario, which instead marks that scenario "error" and
    keeps going) — this should be rare."""

    strategy_name: str
    shared_config: Dict[str, Any]
    scenarios: List[BatchJobScenario] = field(default_factory=list)
    status: str = "pending"
    id: Optional[int] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @property
    def total_scenarios(self) -> int:
        return len(self.scenarios)

    @property
    def processed_scenarios(self) -> int:
        return sum(1 for s in self.scenarios if s.status in ("done", "skipped", "invalid", "error"))
