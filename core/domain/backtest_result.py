# core/domain/backtest_result.py
"""A saved backtest run's identity (what was actually tested) plus its
result, so a strategy's tuning history survives across sessions and can be
compared without manually screenshotting Excel — see runners/backtesting/
and backtest_server.py, which produce and persist these.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class BacktestRunParams:
    """Every input that changes which trades a backtest produces — this is
    the dedup identity. Two runs with identical params (down to symbols,
    date range, and every risk/sizing setting) are the same result and
    never get a second stored row; re-running identical params updates
    that row in place instead. Capital is deliberately excluded — it only
    rescales metrics (drawdown %, Sharpe), it never changes which trades
    fire, so it doesn't belong in the identity."""

    strategy_name: str
    symbols: str  # sorted, comma-joined uppercase list, or "WATCHLIST"
    timeframe: str
    date_from: date
    date_to: date
    quantity: int
    stoploss_pct: float
    target_pct: float
    trailing_pct: float
    max_cycles_per_day: int
    start_time: str
    end_time: str
    charges_enabled: bool


@dataclass(frozen=True)
class BacktestResult:
    """`result` is deliberately a flexible dict (metrics, breakdowns,
    equity curve, symbols actually used) rather than fixed columns — that
    shape already varies release to release and doesn't need its own
    migration every time a new metric is added. Trade-level data is never
    included here; it's cheap to regenerate by re-running these exact
    params."""

    params: BacktestRunParams
    result: Dict[str, Any]
    id: Optional[int] = None
    created_at: Optional[datetime] = None
