"""Pure performance-metrics calculation over a strategy's trade history.

No I/O, no ports — same spirit as PortfolioSnapshot.realized_pnl. Works
identically for any strategy's trades: nothing here is ORB-specific, so a
second/third deployed strategy gets these metrics for free.

Every "not enough data yet" case returns None for that field rather than
a misleading 0 or an exception — callers (the API layer) pass that
through as-is; the frontend is responsible for rendering "N/A".

Everything below operates on plain List[Trade] and is the single source
of truth for every derived number the analytics dashboard shows — chart
data (equity curve, drawdown series, ...) is computed here too, never
recomputed client-side, so a strategy never needs special-casing anywhere
but this file.
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Literal, Optional

from core.domain.models import Trade

Bucket = Literal["daily", "weekly", "monthly"]


@dataclass(frozen=True)
class PerformanceMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Optional[float]  # percent
    profit_factor: Optional[float]  # gross_profit / abs(gross_loss); None if no losses yet
    gross_profit: float
    gross_loss: float  # negative or zero
    total_pnl: float
    avg_win: Optional[float]  # mean P&L of winning trades; None if no wins yet
    avg_loss: Optional[float]  # mean P&L of losing trades (negative); None if no losses yet
    max_drawdown: float  # currency, off the cumulative-P&L equity curve
    max_drawdown_pct: Optional[float]  # relative to capital
    avg_r_multiple: Optional[float]  # mean(pnl / risk) over trades with a known entry SL
    sharpe_ratio: Optional[float]  # daily-bucketed, annualized; None if <2 trading days


def compute_performance_metrics(trades: List[Trade], capital: float) -> PerformanceMetrics:
    if not trades:
        return PerformanceMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=None,
            profit_factor=None,
            gross_profit=0.0,
            gross_loss=0.0,
            total_pnl=0.0,
            avg_win=None,
            avg_loss=None,
            max_drawdown=0.0,
            max_drawdown_pct=None,
            avg_r_multiple=None,
            sharpe_ratio=None,
        )

    ordered = _sorted_by_close(trades)
    total_trades = len(ordered)

    wins = [t for t in ordered if t.pnl > 0]
    losses = [t for t in ordered if t.pnl < 0]

    win_rate = (len(wins) / total_trades) * 100
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = sum(t.pnl for t in losses)
    total_pnl = sum(t.pnl for t in ordered)
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss < 0 else None
    avg_win = (gross_profit / len(wins)) if wins else None
    avg_loss = (gross_loss / len(losses)) if losses else None

    max_drawdown = _max_drawdown(ordered)
    max_drawdown_pct = (max_drawdown / capital) * 100 if capital > 0 else None

    avg_r_multiple = _avg_r_multiple(ordered)
    sharpe_ratio = _sharpe_ratio(ordered, capital)

    return PerformanceMetrics(
        total_trades=total_trades,
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=win_rate,
        profit_factor=profit_factor,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        total_pnl=total_pnl,
        avg_win=avg_win,
        avg_loss=avg_loss,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
        avg_r_multiple=avg_r_multiple,
        sharpe_ratio=sharpe_ratio,
    )


def _sorted_by_close(trades: List[Trade]) -> List[Trade]:
    return sorted(trades, key=lambda t: t.closed_at)


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


def _daily_pnl(trades: List[Trade]) -> Dict[date, float]:
    daily: Dict[date, float] = defaultdict(float)
    for t in trades:
        daily[t.closed_at.date()] += t.pnl
    return daily


def _sharpe_from_returns(daily_returns_pct: List[float]) -> Optional[float]:
    if len(daily_returns_pct) < 2:
        return None

    mean_return = sum(daily_returns_pct) / len(daily_returns_pct)
    variance = sum((r - mean_return) ** 2 for r in daily_returns_pct) / (
        len(daily_returns_pct) - 1
    )
    std_dev = math.sqrt(variance)

    return (mean_return / std_dev) * math.sqrt(252) if std_dev > 0 else None


def _sharpe_ratio(ordered_trades: List[Trade], capital: float) -> Optional[float]:
    if capital <= 0:
        return None

    daily_returns_pct = [(pnl / capital) * 100 for pnl in _daily_pnl(ordered_trades).values()]
    return _sharpe_from_returns(daily_returns_pct)


def _bucket_start(d: date, bucket: Bucket) -> date:
    if bucket == "daily":
        return d
    if bucket == "weekly":
        return d - timedelta(days=d.weekday())
    if bucket == "monthly":
        return d.replace(day=1)
    raise ValueError(f"Unknown bucket: {bucket!r}")


# ---------------------------------------------------------------------------
# Chart-oriented aggregations. Same rule as above: strategy-agnostic, pure,
# operate on whatever List[Trade] the caller already filtered (by strategy /
# symbol / date range) — no filtering logic lives here.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EquityPoint:
    bucket: date
    cumulative_pnl: float


def equity_curve(trades: List[Trade], bucket: Bucket = "daily") -> List[EquityPoint]:
    """Cumulative P&L, one point per bucket that had at least one closed trade."""
    points: List[EquityPoint] = []
    cumulative = 0.0
    for t in _sorted_by_close(trades):
        cumulative += t.pnl
        b = _bucket_start(t.closed_at.date(), bucket)
        if points and points[-1].bucket == b:
            points[-1] = EquityPoint(bucket=b, cumulative_pnl=cumulative)
        else:
            points.append(EquityPoint(bucket=b, cumulative_pnl=cumulative))
    return points


@dataclass(frozen=True)
class PeriodPnl:
    bucket: date
    pnl: float  # net P&L within this bucket only (not cumulative)


def pnl_by_period(trades: List[Trade], bucket: Bucket = "monthly") -> List[PeriodPnl]:
    totals: Dict[date, float] = defaultdict(float)
    for t in trades:
        totals[_bucket_start(t.closed_at.date(), bucket)] += t.pnl
    return [PeriodPnl(bucket=b, pnl=pnl) for b, pnl in sorted(totals.items())]


@dataclass(frozen=True)
class DrawdownPoint:
    closed_at: datetime
    drawdown: float  # currency, >= 0
    drawdown_pct: Optional[float]  # relative to capital


def drawdown_series(trades: List[Trade], capital: float) -> List[DrawdownPoint]:
    """Running drawdown after every closed trade — the series behind
    _max_drawdown's single number, for the Drawdown chart."""
    points: List[DrawdownPoint] = []
    cumulative = 0.0
    peak = 0.0
    for t in _sorted_by_close(trades):
        cumulative += t.pnl
        peak = max(peak, cumulative)
        dd = peak - cumulative
        dd_pct = (dd / capital) * 100 if capital > 0 else None
        points.append(DrawdownPoint(closed_at=t.closed_at, drawdown=dd, drawdown_pct=dd_pct))
    return points


@dataclass(frozen=True)
class HistogramBucket:
    range_start: float
    range_end: float
    count: int


def profit_distribution(trades: List[Trade], bucket_count: int = 20) -> List[HistogramBucket]:
    """Histogram of per-trade P&L, for the Profit Distribution chart."""
    if not trades:
        return []

    pnls = [t.pnl for t in trades]
    lo, hi = min(pnls), max(pnls)
    if lo == hi:
        return [HistogramBucket(range_start=lo, range_end=hi, count=len(pnls))]

    width = (hi - lo) / bucket_count
    counts = [0] * bucket_count
    for pnl in pnls:
        idx = min(int((pnl - lo) / width), bucket_count - 1)
        counts[idx] += 1

    return [
        HistogramBucket(range_start=lo + i * width, range_end=lo + (i + 1) * width, count=c)
        for i, c in enumerate(counts)
    ]


@dataclass(frozen=True)
class RollingSharpePoint:
    date: date
    sharpe_ratio: Optional[float]


def rolling_sharpe(
    trades: List[Trade], capital: float, window_days: int = 20
) -> List[RollingSharpePoint]:
    """Sharpe ratio recomputed over a trailing window of trading days (days
    that had at least one closed trade), for the Rolling Sharpe chart."""
    if capital <= 0 or not trades:
        return []

    daily = _daily_pnl(trades)
    days = sorted(daily.keys())

    points: List[RollingSharpePoint] = []
    for i, d in enumerate(days):
        window = days[max(0, i - window_days + 1) : i + 1]
        returns = [(daily[wd] / capital) * 100 for wd in window]
        points.append(RollingSharpePoint(date=d, sharpe_ratio=_sharpe_from_returns(returns)))

    return points
