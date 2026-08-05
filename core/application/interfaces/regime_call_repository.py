"""Port: persisted log of every _classify() output (see
services/market_analysis_engine.py) plus the rolling win-rate read that
backs the Decision panel's accuracy stat block.

Write side (log_call) is called from analyze() on every request; read side
(win_rate) is also called from analyze() so the stat rides the same 5s poll
the frontend already does. pending_evaluations/record_return back the
separate background job (runners/paper_trading/regime_call_evaluator.py)
that fills in forward returns once enough time has passed.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

# Matches the return_<horizon> columns on RegimeCallRecord.
Horizon = str  # "15m" | "30m" | "60m"


@dataclass(frozen=True)
class RegimeCall:
    symbol: str
    logged_at: datetime  # last CLOSED candle's timestamp, naive local (IST) — see market_analysis_engine.py
    ltp: float
    regime: str
    trend_strength: str
    volatility_state: str
    confidence_score: int
    decision: str
    suggested_side: Optional[str]


@dataclass(frozen=True)
class PendingEvaluation:
    id: int
    symbol: str
    logged_at: datetime
    ltp: float
    suggested_side: Optional[str]


@dataclass(frozen=True)
class WinRateStat:
    win_rate: float  # percent, 0-100
    wins: int
    n: int


class IRegimeCallRepository(ABC):
    @abstractmethod
    def log_call(self, call: RegimeCall) -> None:
        """No-op if a call for (symbol, logged_at) is already logged —
        callers poll every 5s but the underlying candle only changes once
        a minute, so this is the dedup point."""

    @abstractmethod
    def win_rate(self, symbol: str, decision: str, horizon: Horizon, since: datetime) -> WinRateStat:
        """Win rate among calls for this exact (symbol, decision) pair,
        logged at or after `since`, whose return_<horizon> has resolved.
        A call "wins" if the forward return moved in the direction its
        suggested_side implied."""

    @abstractmethod
    def pending_evaluations(self, horizon: Horizon, now: datetime) -> List[PendingEvaluation]:
        """Calls old enough for `horizon` to have elapsed whose
        return_<horizon> hasn't been filled in yet."""

    @abstractmethod
    def record_return(self, call_id: int, horizon: Horizon, pct_return: float) -> None:
        ...
