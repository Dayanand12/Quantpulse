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
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.application.interfaces.deployment_repository import IDeploymentRepository
from core.domain.metrics import PerformanceMetrics, compute_performance_metrics
from core.domain.models import Trade
from infrastructure.persistence.database import unit_of_work
from infrastructure.persistence.models import TradeRecord
from infrastructure.persistence.sql_trade_repository import record_to_trade

TRADE_COLUMNS = [
    "Time", "Deployment ID", "Strategy", "Symbol", "Side",
    "Qty", "Entry", "Exit", "PnL", "PnL %", "Initial SL",
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
        "PnL %": pnl_pct,
        "Initial SL": trade.initial_stop_loss,
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
        "Total P&L": round(m.total_pnl, 2),
        "Max Drawdown": round(m.max_drawdown, 2),
        "Max Drawdown %": round(m.max_drawdown_pct, 2) if m.max_drawdown_pct is not None else None,
        "Avg R-Multiple": round(m.avg_r_multiple, 2) if m.avg_r_multiple is not None else None,
        "Sharpe Ratio": round(m.sharpe_ratio, 2) if m.sharpe_ratio is not None else None,
    }


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

    filename = os.path.join(output_dir, f"EOD_Report_{report_date.strftime('%Y%m%d')}.xlsx")
    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        trades_df.to_excel(writer, sheet_name="Trades", index=False)
        metrics_df.to_excel(writer, sheet_name="Strategy Metrics", index=False)

    return filename
