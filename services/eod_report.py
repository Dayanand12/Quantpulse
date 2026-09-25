# backend/eod_report.py
"""End-of-day report: every trade closed on a given day, plus per-
strategy/deployment performance metrics, written to a single Excel
workbook.

Reads from the `trades` table (infrastructure/persistence/sql_trade_journal.py
persists every closed trade there as it happens), not PaperBroker's
in-memory trade_log — so a report survives a backend restart, and any
past day can be regenerated later for analysis, not just "today".
"""

import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.application.interfaces.deployment_repository import IDeploymentRepository
from core.domain.market_condition import split_market_condition
from core.domain.metrics import PerformanceMetrics, compute_performance_metrics
from core.domain.models import Trade
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import TradeRecord
from infrastructure.persistence.sql_trade_repository import record_to_trade

TRADE_COLUMNS = [
    "Time", "Deployment ID", "Strategy", "Symbol", "Side",
    "Qty", "Entry", "Exit", "PnL", "Charges", "Net PnL", "PnL %", "Initial SL",
    "Market Condition", "Entry RSI", "Entry ADX", "Entry ATR %",
    "Entry VWAP", "Entry Volume Ratio",
]


def _fetch_trades_for_day(session_factory: sessionmaker, report_date: date) -> List[Trade]:
    start = datetime.combine(report_date, datetime.min.time())
    end = start + timedelta(days=1)

    with unit_of_work(session_factory) as session:
        records = session.scalars(
            select(TradeRecord)
            .where(TradeRecord.closed_at >= start, TradeRecord.closed_at < end)
            .order_by(TradeRecord.closed_at)
        )
        return [record_to_trade(r) for r in records]


def _fetch_all_trades(session_factory: sessionmaker) -> List[Trade]:
    with unit_of_work(session_factory) as session:
        records = session.scalars(select(TradeRecord).order_by(TradeRecord.closed_at))
        return [record_to_trade(r) for r in records]


def _trade_row(trade: Trade) -> dict:
    pnl_pct = None
    if trade.entry_price and trade.quantity:
        pnl_pct = round((trade.pnl / (trade.entry_price * trade.quantity)) * 100, 3)

    return {
        "Time": trade.closed_at.strftime("%H:%M:%S"),
        "Deployment ID": trade.deployment_id or "—",
        "Strategy": trade.strategy_name or "—",
        "Symbol": trade.symbol,
        "Side": trade.side.value,
        "Qty": trade.quantity,
        "Entry": trade.entry_price,
        "Exit": trade.exit_price,
        "PnL": round(trade.pnl, 2),
        "Charges": round(trade.charges, 2) if trade.charges is not None else None,
        "Net PnL": round(trade.net_pnl, 2) if trade.net_pnl is not None else round(trade.pnl, 2),
        "PnL %": pnl_pct,
        "Initial SL": trade.initial_stop_loss,
        "Market Condition": trade.market_condition,
        "Entry RSI": round(trade.entry_rsi, 2) if trade.entry_rsi is not None else None,
        "Entry ADX": round(trade.entry_adx, 2) if trade.entry_adx is not None else None,
        "Entry ATR %": round(trade.entry_atr_pct, 2) if trade.entry_atr_pct is not None else None,
        "Entry VWAP": round(trade.entry_vwap, 2) if trade.entry_vwap is not None else None,
        "Entry Volume Ratio": round(trade.entry_volume_ratio, 2)
        if trade.entry_volume_ratio is not None
        else None,
    }


def _metrics_row(label: str, capital: float, m: PerformanceMetrics) -> dict:
    return {
        "Strategy": label,
        "Capital": capital,
        "Total Trades": m.total_trades,
        "Win Rate %": round(m.win_rate, 2) if m.win_rate is not None else None,
        "Profit Factor": round(m.profit_factor, 2) if m.profit_factor is not None else None,
        "Gross Profit": round(m.gross_profit, 2),
        "Gross Loss": round(m.gross_loss, 2),
        "Gross P&L (before charges)": round(m.gross_total_pnl, 2),
        "Total Charges": round(m.total_charges, 2),
        "Total P&L": round(m.total_pnl, 2),
        "Max Drawdown": round(m.max_drawdown, 2),
        "Max Drawdown %": round(m.max_drawdown_pct, 2) if m.max_drawdown_pct is not None else None,
        "Avg R-Multiple": round(m.avg_r_multiple, 2) if m.avg_r_multiple is not None else None,
        "Sharpe Ratio": round(m.sharpe_ratio, 2) if m.sharpe_ratio is not None else None,
    }


def _write_report(
    trades: List[Trade],
    deployment_repository: IDeploymentRepository,
    filename: str,
) -> str:
    trades_by_deployment: Dict[Optional[str], List[Trade]] = defaultdict(list)
    for trade in trades:
        trades_by_deployment[trade.deployment_id].append(trade)

    deployments = deployment_repository.list_deployments()
    seen_deployment_ids = set()
    metrics_rows = []

    for deployment in deployments:
        seen_deployment_ids.add(deployment.id)
        deployment_trades = trades_by_deployment.get(deployment.id, [])
        metrics = compute_performance_metrics(deployment_trades, deployment.capital)
        metrics_rows.append(
            _metrics_row(f"{deployment.strategy_name} ({deployment.id})", deployment.capital, metrics)
        )

    # Trades tagged with a deployment that's since been deleted still show
    # up here — capital is unknown for it, so %-of-capital metrics are None.
    for deployment_id, deployment_trades in trades_by_deployment.items():
        if deployment_id in seen_deployment_ids:
            continue
        strategy_name = deployment_trades[0].strategy_name or "unknown strategy"
        label = f"{strategy_name} ({deployment_id or 'no deployment tag'})"
        metrics = compute_performance_metrics(deployment_trades, 0)
        metrics_rows.append(_metrics_row(label, 0, metrics))

    total_capital = sum(d.capital for d in deployments)
    overall = compute_performance_metrics(trades, total_capital)
    metrics_rows.append(_metrics_row("ALL STRATEGIES (combined)", total_capital, overall))

    trades_df = pd.DataFrame([_trade_row(t) for t in trades], columns=TRADE_COLUMNS)
    metrics_df = pd.DataFrame(metrics_rows)

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        trades_df.to_excel(writer, sheet_name="Trades", index=False)
        metrics_df.to_excel(writer, sheet_name="Strategy Metrics", index=False)

    return filename


def generate_eod_report(
    session_factory: sessionmaker,
    deployment_repository: IDeploymentRepository,
    report_date: Optional[date] = None,
    output_dir: str = "reports",
) -> str:
    """Writes reports/EOD_Report_<YYYYMMDD>.xlsx for `report_date` (default
    today) and returns its path. Re-running for the same day overwrites
    that day's file rather than piling up duplicates.
    """
    report_date = report_date or date.today()
    os.makedirs(output_dir, exist_ok=True)

    trades = _fetch_trades_for_day(session_factory, report_date)
    filename = os.path.join(output_dir, f"EOD_Report_{report_date.strftime('%Y%m%d')}.xlsx")
    return _write_report(trades, deployment_repository, filename)


def generate_all_time_report(
    session_factory: sessionmaker,
    deployment_repository: IDeploymentRepository,
    output_dir: str = "reports",
) -> str:
    """Writes reports/All_Time_Report.xlsx covering every trade ever
    recorded (not just one day) — same shape as the daily report, just
    unfiltered. Re-running overwrites the same file rather than piling up
    duplicates, same convention as the daily report.
    """
    os.makedirs(output_dir, exist_ok=True)

    trades = _fetch_all_trades(session_factory)
    filename = os.path.join(output_dir, "All_Time_Report.xlsx")
    return _write_report(trades, deployment_repository, filename)


# Below this many trades, a win rate/profit factor reads as noise (a
# couple of lucky/unlucky trades looking "hot"/"cold") — same guard the
# Performance tab's heatmap uses (frontend/src/components/analytics/
# StrategyHeatmap.tsx's MIN_SAMPLE), so a spreadsheet reader gets the
# same "don't trust this yet" signal the UI already shows instead of
# mistaking a 2-trade 100%-win-rate row for an edge.
_MIN_SAMPLE_SIZE = 10


def _sample_flag(total_trades: int) -> str:
    return "OK" if total_trades >= _MIN_SAMPLE_SIZE else f"Low (<{_MIN_SAMPLE_SIZE})"


def _condition_breakdown_rows(trades: List[Trade]) -> List[dict]:
    """One row per (strategy, market_condition) pair with at least one
    trade — Trend/Volume/VWAP split into their own columns (see
    core/domain/market_condition.py::split_market_condition) alongside the
    combined label, so the sheet can be sorted/filtered on any of them to
    see which strategy wins in which condition, not just eyeballed off the
    Performance tab's heatmap. Trades without a recorded market_condition
    (pre-dates that field, or missing entry indicators) are excluded
    rather than lumped into a misleading "unknown" row — same convention
    as core/domain/metrics.py::heatmap_by_strategy_and_condition."""
    groups: Dict[tuple, List[Trade]] = defaultdict(list)
    for t in trades:
        if not t.strategy_name or not t.market_condition:
            continue
        groups[(t.strategy_name, t.market_condition)].append(t)

    rows = []
    for (strategy_name, condition), group in groups.items():
        trend, volume, vwap = split_market_condition(condition)
        m = compute_performance_metrics(group, capital=0)
        rows.append({
            "Strategy": strategy_name,
            "Market Condition": condition,
            "Trend": trend,
            "Volume": volume,
            "VWAP Position": vwap or "—",
            "Trades": m.total_trades,
            "Win Rate %": round(m.win_rate, 2) if m.win_rate is not None else None,
            "Profit Factor": round(m.profit_factor, 2) if m.profit_factor is not None else None,
            "Total P&L": round(m.total_pnl, 2),
            "Avg R-Multiple": round(m.avg_r_multiple, 2) if m.avg_r_multiple is not None else None,
            "Sample Size": _sample_flag(m.total_trades),
        })
    return sorted(rows, key=lambda r: r["Trades"], reverse=True)


# Dimension -> column header, for every regime field core/domain/
# regime_snapshot.py computes at entry — consolidated into ONE sheet with
# a "Dimension" column below (_regime_breakdown_rows) instead of five
# separate sheets, so "which strategy wins when VIX is High" is one Excel
# filter away instead of a sheet hunt.
_REGIME_DIMENSIONS = {
    "regime_trend": "Trend",
    "regime_volatility": "Volatility",
    "index_trend": "Index Trend",
    "vix_bucket": "VIX Level",
    "session_phase": "Session",
}


def _regime_breakdown_rows(trades: List[Trade]) -> List[dict]:
    """One row per (strategy, dimension, value) triple with at least one
    trade, across every regime dimension in _REGIME_DIMENSIONS. Trades
    where a given dimension wasn't recorded (pre-dates regime logging, or
    that dimension's inputs weren't available — e.g. INDIA VIX off the
    watchlist) are simply excluded from that dimension's rows, same
    convention as _condition_breakdown_rows above."""
    rows = []
    for field, label in _REGIME_DIMENSIONS.items():
        groups: Dict[tuple, List[Trade]] = defaultdict(list)
        for t in trades:
            value = getattr(t, field)
            if not t.strategy_name or not value:
                continue
            groups[(t.strategy_name, value)].append(t)

        for (strategy_name, value), group in groups.items():
            m = compute_performance_metrics(group, capital=0)
            rows.append({
                "Strategy": strategy_name,
                "Dimension": label,
                "Value": value,
                "Trades": m.total_trades,
                "Win Rate %": round(m.win_rate, 2) if m.win_rate is not None else None,
                "Profit Factor": round(m.profit_factor, 2) if m.profit_factor is not None else None,
                "Total P&L": round(m.total_pnl, 2),
                "Avg R-Multiple": round(m.avg_r_multiple, 2) if m.avg_r_multiple is not None else None,
                "Sample Size": _sample_flag(m.total_trades),
            })
    return sorted(rows, key=lambda r: r["Trades"], reverse=True)


def export_performance_report(
    trades: List[Trade],
    by_strategy: List[dict],
    filters: Dict[str, Optional[str]],
) -> bytes:
    """The Performance tab's "Download Report" button — the exact trades/
    by_strategy breakdown server/main.py's /api/analytics/summary already
    computed for whatever filters are active on screen, as a workbook:
    the filters that produced this data (so the file is self-explanatory
    once it's out of the browser), the per-strategy summary table shown
    on screen, a per-(strategy, market condition) breakdown, and a per-
    (strategy, regime dimension, value) breakdown (Trend/Volatility/Index
    Trend/VIX Level/Session — core/domain/regime_snapshot.py) for
    sorting/filtering on which condition or regime a strategy actually
    wins in. `by_strategy` entries carry a raw PerformanceMetrics object
    (not yet asdict'd) — same list server/main.py builds before
    serializing it for the JSON response.
    """
    filters_df = pd.DataFrame([
        {"Filter": "Strategy", "Value": filters.get("strategy") or "All"},
        {"Filter": "Symbol", "Value": filters.get("symbol") or "All"},
        {"Filter": "Date From", "Value": filters.get("date_from") or "—"},
        {"Filter": "Date To", "Value": filters.get("date_to") or "—"},
        {"Filter": "Chart Bucketing", "Value": filters.get("timeframe") or "daily"},
        {"Filter": "Generated At", "Value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    ])

    summary_rows = []
    for s in by_strategy:
        row = _metrics_row(s["strategy_name"], s.get("capital", 0), s["metrics"])
        row["Timeframe"] = s.get("timeframe") or "—"
        summary_rows.append(row)
    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        cols = [c for c in summary_df.columns if c != "Timeframe"]
        cols.insert(1, "Timeframe")
        summary_df = summary_df[cols]

    condition_df = pd.DataFrame(_condition_breakdown_rows(trades))
    regime_df = pd.DataFrame(_regime_breakdown_rows(trades))

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        filters_df.to_excel(writer, sheet_name="Filters Applied", index=False)
        summary_df.to_excel(writer, sheet_name="Strategy Summary", index=False)
        condition_df.to_excel(writer, sheet_name="By Market Condition", index=False)
        regime_df.to_excel(writer, sheet_name="By Regime", index=False)
    return buffer.getvalue()
