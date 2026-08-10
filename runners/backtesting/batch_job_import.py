# runners/backtesting/batch_job_import.py
"""Parses an uploaded Excel workbook of parameter scenarios into
BatchJobScenario rows for one strategy — the column shape matches
runners/backtesting/report.py::export_stored_results_to_excel exactly (a
Label column + the risk/sizing columns + one column per tuned parameter,
everything else ignored), so Export -> edit -> re-upload round-trips
through the same file format without a separate "import template" to
learn. See runners/backtesting/report.py::build_blank_scenario_template
for the "start from nothing" version of the same shape.

Two kinds of column, both read PER ROW:
- Risk/sizing/date-range columns (Timeframe, Quantity, Capital, Stop Loss
  %, Target %, Trailing %, Max Cycles/Day, Start Time, End Time, Charges
  Enabled, Date From, Date To) — a blank cell means "use the job's shared
  setting" (see core/domain/batch_job.py::BatchJobScenario.
  config_overrides), not zero. Date From/Date To being per-row is what
  makes "test this strategy year by year" possible: one row per year,
  same parameters, each with its own date range.
- Strategy parameter columns — whatever's left after the risk/sizing and
  known-ignored columns are accounted for, validated against the
  strategy's actual conditions.json "parameters" keys.

Row-level validation only, never column-level silent-drop: a row with ANY
problem (an unrecognized parameter name, a bad risk/sizing value, a
non-numeric value) is marked "invalid" as a WHOLE row rather than quietly
running with that one column ignored — a typo'd override should never
silently become "no override," since that's a different scenario than the
one actually intended. See core/domain/batch_job.py's "invalid" scenario
status — these rows are skipped, not run, and the reason is kept for the
caller to report back.
"""

import datetime as dt
import math
import re
from io import BytesIO
from typing import Callable, Dict, List, Set, Tuple

import pandas as pd

from core.domain.batch_job import BatchJobScenario
from runners.paper_trading.live_engine import SUPPORTED_TIMEFRAMES

_HHMM_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?$")  # groups: hour, minute


def _parse_timeframe(value) -> str:
    text = str(value).strip()
    if text not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"unsupported timeframe {text!r} (expected one of {', '.join(SUPPORTED_TIMEFRAMES)})")
    return text


def _parse_hhmm(value) -> str:
    # Excel auto-formats a cell you type "9:20" into as a native TIME
    # value, not text — openpyxl/pandas then hand it back as a real
    # datetime.time (or datetime.datetime/pd.Timestamp if the cell also
    # carries a date), never the string "09:20". Handle both: the
    # object form (the common case if you just typed a time into the
    # cell) and a plain "HH:MM" or "HH:MM:SS" string (if the cell was
    # formatted as Text, or came from a tool that writes strings).
    if isinstance(value, dt.datetime):
        return value.strftime("%H:%M")
    if isinstance(value, dt.time):
        return value.strftime("%H:%M")
    text = str(value).strip()
    match = _HHMM_PATTERN.match(text)
    if not match:
        raise ValueError(f"{text!r} isn't a valid HH:MM (24h) time")
    return f"{match.group(1)}:{match.group(2)}"


def _parse_float(value) -> float:
    return float(value)


def _parse_int(value) -> int:
    return int(float(value))  # tolerate Excel storing whole numbers as e.g. 50.0


def _parse_date_cell(value) -> str:
    # Same reasoning as _parse_hhmm: typing a date into a cell auto-
    # formats it as a native Excel date, so pandas hands back a real
    # datetime.datetime/pd.Timestamp (pd.Timestamp subclasses
    # datetime.datetime, so the isinstance check below catches both) —
    # not the string "2023-01-01". Handle both that and a plain ISO
    # string (a Text-formatted cell, or a value typed by hand).
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value).strip()
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError(f"{text!r} isn't a valid date (expected YYYY-MM-DD)")


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "y"):
        return True
    if text in ("false", "0", "no", "n"):
        return False
    raise ValueError(f"{value!r} isn't a recognizable true/false value")


# Column name -> (BatchJobScenario.config_overrides key, parser). Column
# names match export_stored_results_to_excel()'s output exactly, so a
# downloaded comparison sheet is a valid upload as-is.
_CONFIG_COLUMNS: Dict[str, Tuple[str, Callable]] = {
    "Timeframe": ("timeframe", _parse_timeframe),
    "Quantity": ("quantity", _parse_int),
    "Capital (₹)": ("capital", _parse_float),
    "Capital": ("capital", _parse_float),  # tolerate either header spelling
    "Stop Loss %": ("stoploss_pct", _parse_float),
    "Target %": ("target_pct", _parse_float),
    "Trailing %": ("trailing_pct", _parse_float),
    "Max Cycles/Day": ("max_cycles_per_day", _parse_int),
    "Start Time": ("start_time", _parse_hhmm),
    "End Time": ("end_time", _parse_hhmm),
    "Charges Enabled": ("charges", _parse_bool),
    # Per-row date range — this is what makes "one row per year" (2023,
    # 2024, 2025, ...) work: each row tests the SAME strategy/parameters
    # over its own window instead of one date range for the whole job.
    "Date From": ("date_from", _parse_date_cell),
    "Date To": ("date_to", _parse_date_cell),
}

# Columns that are informational-only when re-importing an exported
# comparison sheet — symbols stay job-level (set once for the whole
# upload, not per scenario) and every output metric column is just
# whatever that row's run produced, never an input.
_IGNORED_COLUMNS = {
    "Label", "Result ID", "Symbols",
    "Total Trades", "Win Rate %", "Profit Factor", "Gross P&L (before charges)",
    "Total Charges", "Total P&L", "Max Drawdown", "Max Drawdown %",
    "Avg R-Multiple", "Sharpe Ratio", "Created At",
}


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def parse_scenarios_from_excel(content: bytes, valid_parameter_names: Set[str]) -> List[BatchJobScenario]:
    """`valid_parameter_names`: the strategy's real conditions.json
    "parameters" keys (see runners/backtesting/batch_runner.py::
    merge_condition_overrides, which enforces the same rule at run time —
    checking it here too means a typo surfaces in seconds, not after
    however long the queue in front of it takes to churn through).

    A row where every parameter AND config column is blank is silently
    skipped (almost always a trailing blank row Excel leaves behind) —
    not counted as invalid, since nothing was actually attempted."""
    df = pd.read_excel(BytesIO(content))
    param_columns = [c for c in df.columns if c not in _CONFIG_COLUMNS and c not in _IGNORED_COLUMNS]

    scenarios: List[BatchJobScenario] = []
    for i, row in enumerate(df.to_dict(orient="records")):
        excel_row_number = i + 2  # header occupies row 1 in the spreadsheet

        overrides: Dict[str, float] = {}
        config_overrides: Dict[str, object] = {}
        problems: List[str] = []

        for col, (config_key, parser) in _CONFIG_COLUMNS.items():
            value = row.get(col)
            if _is_blank(value):
                continue
            try:
                config_overrides[config_key] = parser(value)
            except (TypeError, ValueError) as e:
                problems.append(f"{col}: {e}")

        unknown_columns: List[str] = []
        non_numeric_columns: List[str] = []
        for col in param_columns:
            value = row.get(col)
            if _is_blank(value):
                continue
            if col not in valid_parameter_names:
                unknown_columns.append(str(col))
                continue
            try:
                overrides[col] = float(value)
            except (TypeError, ValueError):
                non_numeric_columns.append(str(col))

        if unknown_columns:
            problems.append(f"unknown parameter(s): {', '.join(unknown_columns)}")
        if non_numeric_columns:
            problems.append(f"non-numeric value(s) for: {', '.join(non_numeric_columns)}")

        if not overrides and not config_overrides and not problems:
            continue  # nothing in this row at all — not a real scenario

        label_value = row.get("Label")
        label = str(label_value).strip() if not _is_blank(label_value) else f"Row {excel_row_number}"

        if problems:
            scenarios.append(BatchJobScenario(
                label=label, overrides=overrides, config_overrides=config_overrides,
                status="invalid", error="; ".join(problems),
            ))
            continue

        scenarios.append(BatchJobScenario(
            label=label, overrides=overrides, config_overrides=config_overrides, status="pending",
        ))

    return scenarios
