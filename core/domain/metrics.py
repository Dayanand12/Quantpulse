"""Pure performance-metrics calculation over a strategy's trade history.

No I/O, no ports — same spirit as PortfolioSnapshot.realized_pnl. Works
identically for any strategy's trades: nothing here is ORB-specific, so a
second/third deployed strategy gets these metrics for free.

Every "not enough data yet" case returns None for that field rather than
a misleading 0 or an exception — callers (the API layer) pass that
through as-is; the frontend is responsible for rendering "N/A".
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional

from core.domain.models import Trade


@dataclass(frozen=True)
class PerformanceMetrics:
    total_trades: int
    win_rate: Optional[float]  # percent
    profit_factor: Optional[float]  # gross_profit / abs(gross_loss); None if no losses yet
    gross_profit: float
    gross_loss: float  # negative or zero
    total_pnl: float
    max_drawdown: float  # currency, off the cumulative-P&L equity curve
    max_drawdown_pct: Optional[float]  # relative to capital
    avg_r_multiple: Optional[float]  # mean(pnl / risk) over trades with a known entry SL
    sharpe_ratio: Optional[float]  # daily-bucketed, annualized; None if <2 trading days


def compute_performance_metrics(trades: List[Trade], capital: float) -> PerformanceMetrics:
    if not trades:
        return PerformanceMetrics(
            total_trades=0,
            win_rate=None,
            profit_factor=None,
            gross_profit=0.0,
            gross_loss=0.0,
            total_pnl=0.0,
            max_drawdown=0.0,
            max_drawdown_pct=None,
            avg_r_multiple=None,
            sharpe_ratio=None,
        )

    ordered = sorted(trades, key=lambda t: t.closed_at)
    total_trades = len(ordered)

    wins = [t for t in ordered if t.pnl > 0]
    losses = [t for t in ordered if t.pnl < 0]

    win_rate = (len(wins) / total_trades) * 100
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = sum(t.pnl for t in losses)
    total_pnl = sum(t.pnl for t in ordered)
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss < 0 else None

    max_drawdown = _max_drawdown(ordered)
    max_drawdown_pct = (max_drawdown / capital) * 100 if capital > 0 else None

    avg_r_multiple = _avg_r_multiple(ordered)
    sharpe_ratio = _sharpe_ratio(ordered, capital)

    return PerformanceMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        total_pnl=total_pnl,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
        avg_r_multiple=avg_r_multiple,
        sharpe_ratio=sharpe_ratio,
    )


def _max_drawdown(ordered_trades: List[Trade]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in ordered_trades:
        cumulative += t.pnl
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return max_dd


def _avg_r_multiple(ordered_trades: List[Trade]) -> Optional[float]:
    r_multiples = []
    for t in ordered_trades:
        if t.initial_stop_loss is None:
            continue
        risk_per_share = abs(t.entry_price - t.initial_stop_loss)
        if risk_per_share <= 0:
            continue
        r_multiples.append(t.pnl / (risk_per_share * t.quantity))

    return (sum(r_multiples) / len(r_multiples)) if r_multiples else None


def _sharpe_ratio(ordered_trades: List[Trade], capital: float) -> Optional[float]:
    if capital <= 0:
        return None

    daily_pnl = defaultdict(float)
    for t in ordered_trades:
        daily_pnl[t.closed_at.date()] += t.pnl

    daily_returns_pct = [(pnl / capital) * 100 for pnl in daily_pnl.values()]
    if len(daily_returns_pct) < 2:
        return None

    mean_return = sum(daily_returns_pct) / len(daily_returns_pct)
    variance = sum((r - mean_return) ** 2 for r in daily_returns_pct) / (
        len(daily_returns_pct) - 1
    )
    std_dev = math.sqrt(variance)

    return (mean_return / std_dev) * math.sqrt(252) if std_dev > 0 else None
