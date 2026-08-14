# runners/backtesting/batch_runner.py
"""Runs the SAME strategy against N different parameter overrides in
parallel — the "6 panels" feature (user: "there will be 1 strategy and i
will change parameters, not multiple strategies"). Each panel keeps the
strategy's conditions.json structure (the `conditions` list) fixed and
only swaps values in its `parameters` block; none of the N variants is
ever written to strategies/<name>.json on disk.

Reuses parameter_sweep.py's ProcessPoolExecutor pattern: a panel's merged
condition data is shipped to each worker as a plain dict (picklable,
independently reconstructible via ConditionSet.from_dict), not a live
IStrategy instance or a loaded DataFrame — same reasoning as
parameter_sweep.py's _run_one (multiprocessing on Windows uses spawn).

Only strategies built on JsonConditionStrategy (core/domain/
json_condition_strategy.py) — i.e. every strategy with a conditions.json
next to it — can be batch-run this way; a strategy with hand-written
Python screen() logic has no `parameters` block to override.
"""

import datetime as dt
import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

from core.application.interfaces.strategy import IStrategy
from core.domain.charges import ChargeConfig
from core.domain.indicator_registry import IndicatorSpec
from core.domain.models import StrategyConfig, Trade
from core.domain.strategy_conditions import ConditionSet, required_indicators_from_json
from runners.backtesting.engine import run_backtest
from runners.backtesting.historical_loader import load_backtest_csv
from runners.backtesting.result_persistence import read_strategy_params_json


@dataclass(frozen=True)
class PanelSpec:
    label: str
    overrides: Dict[str, float]


@dataclass(frozen=True)
class PanelResult:
    label: str
    overrides: Dict[str, float]
    # Merged conditions.json text this panel actually ran with — becomes
    # BacktestRunParams.strategy_params_json when saved, so each panel's
    # stored row is distinct (and re-running the same overrides updates
    # the same row instead of duplicating it).
    strategy_params_json: str
    trades: List[Trade]


def merge_condition_overrides(strategy_name: str, overrides: Dict[str, float]) -> Tuple[dict, str]:
    """Loads strategies/<name>.json fresh and folds `overrides` into its
    "parameters" block — the "conditions" list itself is untouched, and
    nothing here is ever written back to disk. Raises ValueError for an
    override key the file doesn't already define: a typo'd parameter name
    silently doing nothing (because no condition references it) is worse
    than failing loud before any backtest runs."""
    raw = read_strategy_params_json(strategy_name)
    if not raw:
        raise ValueError(
            f"{strategy_name!r} has no conditions.json — batch parameter overrides need one."
        )
    data = json.loads(raw)
    parameters = dict(data.get("parameters", {}))
    unknown = set(overrides) - set(parameters)
    if unknown:
        raise ValueError(
            f"Unknown parameter(s) for {strategy_name!r}: {', '.join(sorted(unknown))}. "
            f"Defined: {', '.join(sorted(parameters)) or '(none)'}"
        )
    parameters.update(overrides)
    merged = {**data, "parameters": parameters}
    return merged, json.dumps(merged)


def _run_one(args: tuple) -> Tuple[int, str, List[Trade]]:
    (
        strategy_cls, symbol, csv_path, panel_index, conditions_dict,
        config, charge_config, date_from, date_to, extra_indicators,
    ) = args
    df = load_backtest_csv(csv_path)
    conditions = ConditionSet.from_dict(conditions_dict)
    strategy = strategy_cls(conditions=conditions)  # fresh instance, no carried-over state
    trades = run_backtest(
        strategy, symbol, df, config, charge_config=charge_config,
        date_from=date_from, date_to=date_to, extra_indicators=extra_indicators,
    )
    return panel_index, symbol, trades


def run_batch_backtests(
    strategy_cls: Type[IStrategy],
    strategy_name: str,
    panels: List[PanelSpec],
    symbols: List[Tuple[str, str]],
    config: StrategyConfig,
    charge_config: Optional[ChargeConfig] = None,
    date_from: Optional[dt.date] = None,
    date_to: Optional[dt.date] = None,
    max_workers: Optional[int] = None,
) -> Tuple[List[PanelResult], List[str], List[str]]:
    """symbols: [(symbol, csv_path), ...], same convention as
    parameter_sweep.sweep_parameters. Returns (panel_results, symbols_used,
    symbols_missing_data) — data availability is resolved once (it depends
    on the symbol's CSV, not the parameter override) rather than duplicated
    per panel."""
    merged_by_panel = [merge_condition_overrides(strategy_name, panel.overrides) for panel in panels]
    extra_indicators_by_panel: List[List[IndicatorSpec]] = [
        required_indicators_from_json(merged_json) for _, merged_json in merged_by_panel
    ]

    valid_symbols: List[Tuple[str, str]] = []
    symbols_used: List[str] = []
    symbols_missing_data: List[str] = []
    for symbol, csv_path in symbols:
        if Path(csv_path).exists():
            valid_symbols.append((symbol, csv_path))
            symbols_used.append(symbol)
        else:
            symbols_missing_data.append(symbol)

    tasks = [
        (
            strategy_cls, symbol, csv_path, panel_index, merged_by_panel[panel_index][0],
            config, charge_config, date_from, date_to, extra_indicators_by_panel[panel_index],
        )
        for panel_index in range(len(panels))
        for symbol, csv_path in valid_symbols
    ]

    if len(tasks) <= 1:
        # Not worth a process pool for a single (panel, symbol) combination
        # — also keeps this path trivially debuggable when sanity-checking
        # one panel against one symbol.
        results = [_run_one(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(_run_one, tasks))

    trades_by_panel: Dict[int, List[Trade]] = defaultdict(list)
    for panel_index, _symbol, trades in results:
        trades_by_panel[panel_index].extend(trades)

    panel_results = [
        PanelResult(
            label=panels[i].label,
            overrides=panels[i].overrides,
            strategy_params_json=merged_by_panel[i][1],
            trades=trades_by_panel[i],
        )
        for i in range(len(panels))
    ]
    return panel_results, symbols_used, symbols_missing_data
