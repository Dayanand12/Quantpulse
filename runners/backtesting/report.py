# runners/backtesting/report.py
"""Excel reports for backtest runs — same Trades/Metrics row shape as
services/eod_report.py's live EOD reports (imports its private row
builders rather than duplicating that column layout, including the
charges columns), so a backtest report and a live EOD report look and
read the same way.

The By-Symbol/By-Market-Condition/By-Side breakdowns reuse
compute_performance_metrics per group rather than
core/domain/metrics.py's heatmap_by_strategy_and_symbol/_condition —
those are built for the live Performance tab's multi-strategy heatmap and
only carry a reduced HeatmapCell (no charges, no Sharpe, no drawdown);
here there's exactly one strategy per report, so grouping trades directly
and running the same full PerformanceMetrics per group gives the same
columns the Summary sheet has, just sliced.
"""

import os
from collections import defaultdict
from typing import Callable, Dict, List

import pandas as pd

from core.domain.metrics import compute_performance_metrics
from core.domain.models import Trade
from runners.backtesting.parameter_sweep import SweepResult
from services.eod_report import TRADE_COLUMNS, _metrics_row, _trade_row


def _grouped_metrics_rows(trades: List[Trade], key_fn: Callable[[Trade], str]) -> List[dict]:
    """One _metrics_row per distinct key_fn(trade) value — capital=0 since
    a symbol/condition/side slice doesn't have its own capital pool to
    measure drawdown_pct/sharpe against (same reasoning as
    core/domain/metrics.py's HeatmapCell), sorted by trade count
    descending so the most-represented group reads first."""
    groups: Dict[str, List[Trade]] = defaultdict(list)
    for t in trades:
        key = key_fn(t)
        if key is not None:
            groups[key].append(t)

    rows = [
        _metrics_row(key, capital=0, m=compute_performance_metrics(group, capital=0))
        for key, group in groups.items()
    ]
    return sorted(rows, key=lambda r: r["Total Trades"], reverse=True)


def write_backtest_report(
    trades: List[Trade], symbol: str, strategy_name: str, capital: float, filename: str
) -> str:
    """One run's full trade log, overall summary, and breakdowns by
    symbol/market condition/side — five sheets."""
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

    metrics = compute_performance_metrics(trades, capital)
    trades_df = pd.DataFrame([_trade_row(t) for t in trades], columns=TRADE_COLUMNS)
    metrics_df = pd.DataFrame([_metrics_row(f"{strategy_name} ({symbol})", capital, metrics)])
    by_symbol_df = pd.DataFrame(_grouped_metrics_rows(trades, lambda t: t.symbol))
    by_condition_df = pd.DataFrame(_grouped_metrics_rows(trades, lambda t: t.market_condition))
    by_side_df = pd.DataFrame(_grouped_metrics_rows(trades, lambda t: t.side.value))

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        trades_df.to_excel(writer, sheet_name="Trades", index=False)
        metrics_df.to_excel(writer, sheet_name="Summary", index=False)
        by_symbol_df.to_excel(writer, sheet_name="By Symbol", index=False)
        by_condition_df.to_excel(writer, sheet_name="By Market Condition", index=False)
        by_side_df.to_excel(writer, sheet_name="By Side", index=False)

    return filename


def write_sweep_report(
    results: List[SweepResult], symbol: str, strategy_name: str, filename: str
) -> str:
    """One row per config combination's metrics — no per-trade detail
    (that's what write_backtest_report is for, on whichever single config
    the sweep points you to)."""
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

    rows = []
    for r in results:
        c = r.config
        label = f"{strategy_name} ({symbol}) sl={c.stoploss_pct} tp={c.target_pct} trail={c.trailing_pct}"
        row = _metrics_row(label, capital=0, m=r.metrics)
        row.update({
            "Stop Loss %": c.stoploss_pct,
            "Target %": c.target_pct,
            "Trailing %": c.trailing_pct,
            "Quantity": c.quantity,
            "Timeframe": c.timeframe,
        })
        rows.append(row)

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Sweep Results", index=False)

    return filename
