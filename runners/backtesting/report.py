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

import json
import os
from collections import defaultdict
from io import BytesIO
from typing import Callable, Dict, List

import pandas as pd
from openpyxl.styles import PatternFill

from core.domain.backtest_result import BacktestResult
from core.domain.metrics import compute_performance_metrics
from core.domain.models import Trade
from runners.backtesting.batch_job_runner import DEFAULT_SCENARIO_SETTINGS
from runners.backtesting.parameter_sweep import SweepResult
from services.eod_report import TRADE_COLUMNS, _metrics_row, _trade_row

# Column categories for the "Parameter Comparison" sheet — used to
# color-code every cell (not just the header) and to write a plain-text
# "Column Guide" sheet, so handing this file to an LLM never needs the
# split explained in the prompt, and scrolling deep into a long sheet
# still shows at a glance which cells are settable inputs vs computed
# results. "identifier" is its own third bucket (Result ID, Created At) —
# neither a parameter you'd tune nor an outcome the backtest produced.
_IDENTIFIER_COLUMNS = {"Result ID", "Created At"}
_INPUT_COLUMNS = {
    "Label", "Symbols", "Timeframe", "Date From", "Date To", "Quantity",
    "Capital (₹)", "Capital", "Stop Loss %", "Target %", "Trailing %",
    "Max Cycles/Day", "Start Time", "End Time", "Charges Enabled",
}
_OUTPUT_COLUMNS = {
    "Total Trades", "Win Rate %", "Profit Factor", "Gross P&L (before charges)",
    "Total Charges", "Total P&L", "Max Drawdown", "Max Drawdown %",
    "Avg R-Multiple", "Sharpe Ratio",
}

_INPUT_FILL = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
_OUTPUT_FILL = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
_IDENTIFIER_FILL = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")


def _column_category(column: str) -> str:
    """"input" (settable — risk/sizing, or a strategy parameter),
    "output" (the backtest computed it), or "identifier" (record-keeping,
    neither). A column not in any known set is a dynamic strategy
    parameter (adx_threshold, ...) and counts as "input" — it's exactly
    as settable as Stop Loss % is, this function just can't know its name
    ahead of time since it varies per strategy."""
    if column in _IDENTIFIER_COLUMNS:
        return "identifier"
    if column in _OUTPUT_COLUMNS:
        return "output"
    return "input"


def _color_code_columns(worksheet, columns: List[str], row_count: int) -> None:
    """Fills every cell in each column — header AND every data row, not
    just the header — so the input/output split reads at a glance no
    matter how far down a long sheet you've scrolled, without needing to
    scroll back up to the header to remember which group a column is in."""
    fills = {"input": _INPUT_FILL, "output": _OUTPUT_FILL, "identifier": _IDENTIFIER_FILL}
    for col_idx, column in enumerate(columns, start=1):
        fill = fills[_column_category(column)]
        for row_idx in range(1, row_count + 2):  # row 1 is the header; data starts at row 2
            worksheet.cell(row=row_idx, column=col_idx).fill = fill


def _write_column_guide_sheet(writer, columns: List[str]) -> None:
    """A SEPARATE sheet — doesn't touch "Parameter Comparison"'s column
    names or row 1 at all, so parse_scenarios_from_excel() (which only
    ever reads the first sheet, `pd.read_excel`'s sheet_name=0 default)
    is completely unaffected by this existing. Opening the whole
    WORKBOOK — a human, or an LLM asked to read the file — sees in plain
    text which columns are inputs vs outputs, not just color, which a
    text-only reader wouldn't pick up on anyway."""
    guide_rows = [{"Column": col, "Type": _column_category(col).capitalize()} for col in columns]
    guide_rows.append({"Column": "", "Type": ""})
    guide_rows.append({"Column": "Input", "Type": "Something you set — edit these to try a new scenario"})
    guide_rows.append({"Column": "Output", "Type": "Something the backtest produced — read-only result"})
    guide_rows.append({"Column": "Identifier", "Type": "Record-keeping only — not a parameter or a result"})
    pd.DataFrame(guide_rows).to_excel(writer, sheet_name="Column Guide", index=False)


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


def export_stored_results_to_excel(results: List[BacktestResult]) -> bytes:
    """Every stored backtest_results row for one strategy — the exact data
    behind the Analysis tab's Parameter Comparison chart — as a single flat
    sheet, one row per run: its settings, whichever indicator parameters it
    used, and its outcome metrics. Built for handing the whole tuning
    history to a spreadsheet or an LLM at once (the Analysis tab's "Copy"
    button already does this for a single run — this is the same idea for
    every run together). Returns raw .xlsx bytes rather than writing to
    disk, since this is served straight from an HTTP response
    (backtest_server.py), not a CLI report directory.

    Parameter columns are the UNION of every result's conditions.json
    "parameters" keys — a strategy's parameter set can change over its
    tuning history (a threshold added/renamed), and a run predating a given
    key just gets a blank cell for it rather than losing that column.
    """
    param_keys: List[str] = []
    seen_param_keys = set()
    parsed_params: List[Dict[str, float]] = []
    for r in results:
        params: Dict[str, float] = {}
        if r.params.strategy_params_json:
            try:
                params = json.loads(r.params.strategy_params_json).get("parameters", {}) or {}
            except json.JSONDecodeError:
                params = {}
        parsed_params.append(params)
        for key in params:
            if key not in seen_param_keys:
                seen_param_keys.add(key)
                param_keys.append(key)

    rows = []
    for r, params in zip(results, parsed_params):
        p = r.params
        m = r.result.get("metrics", {})
        row = {
            "Result ID": r.id,
            "Symbols": p.symbols,
            "Timeframe": p.timeframe,
            "Date From": p.date_from.isoformat(),
            "Date To": p.date_to.isoformat(),
            "Quantity": p.quantity,
            "Stop Loss %": p.stoploss_pct,
            "Target %": p.target_pct,
            "Trailing %": p.trailing_pct,
            "Max Cycles/Day": p.max_cycles_per_day,
            "Start Time": p.start_time,
            "End Time": p.end_time,
            "Charges Enabled": p.charges_enabled,
        }
        for key in param_keys:
            row[key] = params.get(key)
        row.update({
            "Total Trades": m.get("total_trades"),
            "Win Rate %": m.get("win_rate"),
            "Profit Factor": m.get("profit_factor"),
            "Gross P&L (before charges)": m.get("gross_total_pnl"),
            "Total Charges": m.get("total_charges"),
            "Total P&L": m.get("total_pnl"),
            "Max Drawdown": m.get("max_drawdown"),
            "Max Drawdown %": m.get("max_drawdown_pct"),
            "Avg R-Multiple": m.get("avg_r_multiple"),
            "Sharpe Ratio": m.get("sharpe_ratio"),
            "Created At": r.created_at.isoformat() if r.created_at else None,
        })
        rows.append(row)

    buffer = BytesIO()
    df = pd.DataFrame(rows)
    columns = list(df.columns)
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Parameter Comparison", index=False)
        _color_code_columns(writer.sheets["Parameter Comparison"], columns, len(df))
        _write_column_guide_sheet(writer, columns)
    return buffer.getvalue()


def build_blank_scenario_template(parameter_defaults: Dict[str, float]) -> bytes:
    """The "nothing to export yet" counterpart to
    export_stored_results_to_excel() — one example row built from
    DEFAULT_SCENARIO_SETTINGS (runners/backtesting/batch_job_runner.py,
    the same defaults a batch job falls back to) plus the SELECTED
    strategy's actual conditions.json "parameters" values, so there's
    always something concrete to duplicate/edit rows from even before a
    single backtest has been run. Column names match
    export_stored_results_to_excel()/parse_scenarios_from_excel() exactly
    — this is a valid upload as-is, not just a reference."""
    row = {
        "Label": "Scenario 1",
        "Timeframe": DEFAULT_SCENARIO_SETTINGS["timeframe"],
        "Quantity": DEFAULT_SCENARIO_SETTINGS["quantity"],
        "Capital (₹)": DEFAULT_SCENARIO_SETTINGS["capital"],
        "Stop Loss %": DEFAULT_SCENARIO_SETTINGS["stoploss_pct"],
        "Target %": DEFAULT_SCENARIO_SETTINGS["target_pct"],
        "Trailing %": DEFAULT_SCENARIO_SETTINGS["trailing_pct"],
        "Max Cycles/Day": DEFAULT_SCENARIO_SETTINGS["max_cycles_per_day"],
        "Start Time": DEFAULT_SCENARIO_SETTINGS["start_time"],
        "End Time": DEFAULT_SCENARIO_SETTINGS["end_time"],
        "Charges Enabled": DEFAULT_SCENARIO_SETTINGS["charges"],
        # Left blank on purpose — that means "use whatever's set on the
        # upload form" (DEFAULT_SCENARIO_SETTINGS's None). Fill these in
        # per row (e.g. duplicate this row 3x with 2023/2024/2025) to test
        # the same strategy year by year instead of over one shared range.
        "Date From": DEFAULT_SCENARIO_SETTINGS["date_from"],
        "Date To": DEFAULT_SCENARIO_SETTINGS["date_to"],
    }
    row.update(parameter_defaults)

    buffer = BytesIO()
    df = pd.DataFrame([row])
    columns = list(df.columns)
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Parameter Comparison", index=False)
        _color_code_columns(writer.sheets["Parameter Comparison"], columns, len(df))
        _write_column_guide_sheet(writer, columns)
    return buffer.getvalue()


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
