# runners/backtesting/parameter_sweep.py
"""Runs the same strategy backtest across a grid of StrategyConfig values,
over one or many symbols, in parallel — each (symbol, config) combination
is an independent, sequential backtest (see the GPU-vs-multiprocessing
discussion this was scoped against: this strategy logic is inherently
sequential per run, so CPU process-parallelism across combinations is the
right lever, not GPU/vectorizing the strategy logic itself). Multiple
symbols for the same config are aggregated into one SweepResult, so
"how does this config do across my whole watchlist" is a single ranked
number, not 50 separate ones to eyeball.

Workers take a strategy CLASS and a CSV path, not a live IStrategy instance
or a loaded DataFrame — multiprocessing on Windows uses spawn, which needs
picklable, independently-reconstructible arguments; a strategy instance may
carry per-symbol mutable state (e.g. rsi_mean_reversion's _previous_rsi)
that must start fresh per run, and re-loading the CSV per worker avoids
shipping a potentially large DataFrame through IPC.
"""

import datetime as dt
import itertools
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple, Type

from core.application.interfaces.strategy import IStrategy
from core.domain.charges import ChargeConfig
from core.domain.metrics import PerformanceMetrics, compute_performance_metrics
from core.domain.models import StrategyConfig, Trade
from runners.backtesting.engine import run_backtest
from runners.backtesting.historical_loader import load_equity_csv


@dataclass(frozen=True)
class SweepResult:
    config: StrategyConfig
    metrics: PerformanceMetrics


def build_config_grid(base: StrategyConfig, **param_ranges: Sequence) -> List[StrategyConfig]:
    """build_config_grid(StrategyConfig(), stoploss_pct=[0.5, 0.8], target_pct=[1.5, 2.0])
    -> every combination of the given fields, all other fields held at
    `base`'s values."""
    if not param_ranges:
        return [base]

    names = list(param_ranges.keys())
    return [
        replace(base, **dict(zip(names, combo)))
        for combo in itertools.product(*(param_ranges[n] for n in names))
    ]


def _run_one(args: tuple) -> Tuple[int, List[Trade]]:
    strategy_cls, symbol, csv_path, config_index, config, charge_config, date_from, date_to = args
    df = load_equity_csv(csv_path)
    strategy = strategy_cls()
    trades = run_backtest(
        strategy, symbol, df, config, charge_config=charge_config, date_from=date_from, date_to=date_to
    )
    return config_index, trades


def sweep_parameters(
    strategy_cls: Type[IStrategy],
    symbols: List[Tuple[str, str]],
    config_grid: List[StrategyConfig],
    capital: float = 100_000,
    charge_config: Optional[ChargeConfig] = None,
    max_workers: Optional[int] = None,
    date_from: Optional[dt.date] = None,
    date_to: Optional[dt.date] = None,
) -> List[SweepResult]:
    """symbols: [(symbol, csv_path), ...] — one entry for a single-symbol
    sweep, many for "how does each config do across my whole watchlist."
    Every symbol's trades for the same config_grid index are pooled before
    computing that config's metrics."""
    tasks = [
        (strategy_cls, symbol, csv_path, i, config, charge_config, date_from, date_to)
        for i, config in enumerate(config_grid)
        for symbol, csv_path in symbols
    ]

    if len(tasks) == 1:
        # Not worth spinning up a process pool for a single combination —
        # also makes this path trivially debuggable (no spawn/pickle
        # boundary) when sweeping just to sanity-check one config.
        results = [_run_one(tasks[0])]
    else:
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(_run_one, tasks))

    trades_by_config_index: Dict[int, List[Trade]] = defaultdict(list)
    for config_index, trades in results:
        trades_by_config_index[config_index].extend(trades)

    return [
        SweepResult(
            config=config_grid[i],
            metrics=compute_performance_metrics(trades_by_config_index[i], capital),
        )
        for i in range(len(config_grid))
    ]


def rank_by(results: List[SweepResult], metric: str, reverse: bool = True) -> List[SweepResult]:
    """metric: any PerformanceMetrics field name, e.g. "total_pnl",
    "profit_factor", "sharpe_ratio". Results whose metric is None sort
    last regardless of `reverse` — negating the value (instead of passing
    reverse=True straight to sorted()) keeps that true, since reverse=True
    on the raw tuple would otherwise flip "None last" to "None first" too.
    """
    def sort_key(result: SweepResult):
        value = getattr(result.metrics, metric)
        if value is None:
            return (1, 0.0)
        return (0, -value if reverse else value)

    return sorted(results, key=sort_key)
