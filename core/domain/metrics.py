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


def _net(t: Trade) -> float:
    """Realized P&L for one trade, net of brokerage/STT/exchange/SEBI/stamp
    duty/GST (core/domain/charges.py) — the actual money made or lost, not
    just the raw entry/exit price difference. Falls back to the gross
    `pnl` for the rare trade closed before charges existed and never
    backfilled (see infrastructure/persistence/alembic/versions/
    c8f3a1d9e5b7_...py, which backfills every historical trade), so this
    never silently treats a charge-less trade as free.
    """
    return t.net_pnl if t.net_pnl is not None else t.pnl


@dataclass(frozen=True)
class PerformanceMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Optional[float]  # percent, net-of-charges win/loss
    profit_factor: Optional[float]  # gross_profit / abs(gross_loss); None if no losses yet
    gross_profit: float  # sum of net-P&L winning trades (still net of charges, despite the name — see total_charges)
    gross_loss: float  # negative or zero
    total_pnl: float  # net of charges — this is "realized profit"
    total_charges: float  # sum of every trade's brokerage+STT+exchange+SEBI+stamp duty+GST
    gross_total_pnl: float  # sum of raw entry/exit P&L, before charges — for comparison against total_pnl
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
            total_charges=0.0,
            gross_total_pnl=0.0,
            avg_win=None,
            avg_loss=None,
            max_drawdown=0.0,
            max_drawdown_pct=None,
            avg_r_multiple=None,
            sharpe_ratio=None,
        )

    ordered = _sorted_by_close(trades)
    total_trades = len(ordered)

    wins = [t for t in ordered if _net(t) > 0]
    losses = [t for t in ordered if _net(t) < 0]

    win_rate = (len(wins) / total_trades) * 100
    gross_profit = sum(_net(t) for t in wins)
    gross_loss = sum(_net(t) for t in losses)
    total_pnl = sum(_net(t) for t in ordered)
    total_charges = sum(t.charges if t.charges is not None else 0.0 for t in ordered)
    gross_total_pnl = sum(t.pnl for t in ordered)
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
        total_charges=total_charges,
        gross_total_pnl=gross_total_pnl,
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
        cumulative += _net(t)
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
        r_multiples.append(_net(t) / (risk_per_share * t.quantity))

    return (sum(r_multiples) / len(r_multiples)) if r_multiples else None


def _daily_pnl(trades: List[Trade]) -> Dict[date, float]:
    daily: Dict[date, float] = defaultdict(float)
    for t in trades:
        daily[t.closed_at.date()] += _net(t)
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
        cumulative += _net(t)
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
        totals[_bucket_start(t.closed_at.date(), bucket)] += _net(t)
    return [PeriodPnl(bucket=b, pnl=pnl) for b, pnl in sorted(totals.items())]


@dataclass(frozen=True)
class DrawdownPoint:
    closed_at: datetime
    drawdown: float  # currency, >= 0
    drawdown_pct: Optional[float]  # relative to capital


def drawdown_series(trades: List[Trade], capital: float) -> List[DrawdownPoint]:
    """Running drawdown after every closed trade — the series behind
    _max_drawdown's single number, for the Drawdown chart.

    Collapses trades that closed within the same second into a single
    point (keeping the latest running drawdown for that second) instead of
    emitting one point per trade. The chart renders at second resolution,
    and this system can close dozens of trades in the same wall-clock
    second (e.g. a bulk exit across a large watchlist) — without
    collapsing, those would-be-duplicate timestamps aren't strictly
    ascending, which the charting library rejects outright."""
    points: List[DrawdownPoint] = []
    cumulative = 0.0
    peak = 0.0
    for t in _sorted_by_close(trades):
        cumulative += _net(t)
        peak = max(peak, cumulative)
        dd = peak - cumulative
        dd_pct = (dd / capital) * 100 if capital > 0 else None
        point = DrawdownPoint(closed_at=t.closed_at, drawdown=dd, drawdown_pct=dd_pct)

        if points and points[-1].closed_at.replace(microsecond=0) == t.closed_at.replace(microsecond=0):
            points[-1] = point
        else:
            points.append(point)

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

    pnls = [_net(t) for t in trades]
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


@dataclass(frozen=True)
class HeatmapCell:
    """Capital-independent slice of PerformanceMetrics — a (strategy,
    symbol) or (strategy, market_condition) bucket has no capital of its
    own to measure drawdown_pct/sharpe against, so those aren't included
    here rather than showing a number that isn't meaningful."""

    total_trades: int
    win_rate: Optional[float]
    profit_factor: Optional[float]
    total_pnl: float
    avg_r_multiple: Optional[float]


def _heatmap_cell(trades: List[Trade]) -> HeatmapCell:
    m = compute_performance_metrics(trades, capital=0)
    return HeatmapCell(
        total_trades=m.total_trades,
        win_rate=m.win_rate,
        profit_factor=m.profit_factor,
        total_pnl=m.total_pnl,
        avg_r_multiple=m.avg_r_multiple,
    )


@dataclass(frozen=True)
class HeatmapRow:
    row: str  # strategy_name
    column: str  # symbol, or market_condition
    cell: HeatmapCell


def heatmap_by_strategy_and_symbol(trades: List[Trade]) -> List[HeatmapRow]:
    """One cell per (strategy, symbol) pair that has at least one trade in
    `trades` — callers pass in whatever's already filtered by date range/
    strategy/symbol, so a strategy with no trades in the selected window
    simply doesn't appear (no separate "is this strategy still active"
    check needed elsewhere)."""
    groups: Dict[tuple, List[Trade]] = defaultdict(list)
    for t in trades:
        if not t.strategy_name:
            continue
        groups[(t.strategy_name, t.symbol)].append(t)

    return [
        HeatmapRow(row=strategy, column=symbol, cell=_heatmap_cell(group))
        for (strategy, symbol), group in groups.items()
    ]


def heatmap_by_strategy_and_condition(trades: List[Trade]) -> List[HeatmapRow]:
    """Same as heatmap_by_strategy_and_symbol but bucketed by the entry-time
    market_condition label (core/domain/market_condition.py) instead of
    symbol. Trades without a market_condition (logged before that field
    existed, or missing entry indicators) are excluded rather than lumped
    into a misleading "unknown" bucket."""
    groups: Dict[tuple, List[Trade]] = defaultdict(list)
    for t in trades:
        if not t.strategy_name or not t.market_condition:
            continue
        groups[(t.strategy_name, t.market_condition)].append(t)

    return [
        HeatmapRow(row=strategy, column=condition, cell=_heatmap_cell(group))
        for (strategy, condition), group in groups.items()
    ]


@dataclass(frozen=True)
class StrategyTrendPoint:
    strategy_name: str
    bucket: date
    trades: int
    win_rate: Optional[float]
    profit_factor: Optional[float]
    cumulative_pnl: float  # running total within this strategy's own series only


def strategy_trend(trades: List[Trade], bucket: Bucket = "weekly") -> List[StrategyTrendPoint]:
    """Per-strategy win rate/profit factor/cumulative P&L, one point per
    bucket per strategy — same cadence as equity_curve/pnl_by_period, but
    split by strategy instead of summed across all of them. This is what
    answers "is this strategy still working, or decaying" at a glance,
    which the single blended equity curve can't show. cumulative_pnl
    accumulates within each strategy's own series, so a strategy that
    started mid-window still reads as its own curve from zero rather than
    inheriting an offset from strategies that traded before it existed."""
    by_strategy: Dict[str, List[Trade]] = defaultdict(list)
    for t in trades:
        if t.strategy_name:
            by_strategy[t.strategy_name].append(t)

    points: List[StrategyTrendPoint] = []
    for strategy, strategy_trades in by_strategy.items():
        buckets: Dict[date, List[Trade]] = defaultdict(list)
        for t in strategy_trades:
            buckets[_bucket_start(t.closed_at.date(), bucket)].append(t)

        cumulative = 0.0
        for b in sorted(buckets.keys()):
            m = compute_performance_metrics(buckets[b], capital=0)
            cumulative += m.total_pnl
            points.append(
                StrategyTrendPoint(
                    strategy_name=strategy,
                    bucket=b,
                    trades=m.total_trades,
                    win_rate=m.win_rate,
                    profit_factor=m.profit_factor,
                    cumulative_pnl=cumulative,
                )
            )

    return points


@dataclass(frozen=True)
class CorrelationPair:
    strategy_a: str
    strategy_b: str
    # Pearson correlation of daily P&L between the two strategies over
    # every day either one traded (0-filled on days one was silent, same
    # convention as _daily_pnl); None if fewer than 2 overlapping days or
    # either strategy's daily P&L never varies (correlation undefined).
    correlation: Optional[float]


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return cov / math.sqrt(var_x * var_y)


def strategy_correlation(trades: List[Trade]) -> List[CorrelationPair]:
    """Pairwise correlation of daily P&L between every pair of strategies
    in `trades` — surfaces strategies that look diversified by name but
    actually win and lose on the same days (no real capital-allocation
    benefit to running both). One pair per unique (strategy_a, strategy_b)
    combination, alphabetically ordered so the frontend doesn't need to
    dedupe A×B vs B×A."""
    daily_by_strategy: Dict[str, Dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for t in trades:
        if not t.strategy_name:
            continue
        daily_by_strategy[t.strategy_name][t.closed_at.date()] += _net(t)

    strategies = sorted(daily_by_strategy.keys())
    all_days = sorted({d for daily in daily_by_strategy.values() for d in daily})

    series = {s: [daily_by_strategy[s].get(d, 0.0) for d in all_days] for s in strategies}

    pairs: List[CorrelationPair] = []
    for i, a in enumerate(strategies):
        for b in strategies[i + 1 :]:
            pairs.append(
                CorrelationPair(strategy_a=a, strategy_b=b, correlation=_pearson(series[a], series[b]))
            )
    return pairs
