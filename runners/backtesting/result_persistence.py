# runners/backtesting/result_persistence.py
"""Shared helper for logging a finished backtest run to backtest_results
(core/domain/backtest_result.py) — used by both backtest_server.py (the
UI's /api/backtest/run) and run_backtest.py (the CLI), so a run through
either path dedups against the same stored history.
"""

import datetime as dt
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.application.interfaces.backtest_result_repository import IBacktestResultRepository
from core.domain.backtest_result import BacktestResult, BacktestRunParams
from core.domain.indicator_registry import IndicatorSpec
from core.domain.metrics import compute_performance_metrics, equity_curve
from core.domain.models import StrategyConfig, Trade
from core.domain.strategy_conditions import required_indicators_from_json


def read_strategy_params_json(strategy_name: str) -> str:
    """Raw content of strategies/<name>.json at this exact moment (see
    core/domain/strategy_conditions.py), or "" if this strategy hasn't
    been migrated to condition-JSON yet. Read fresh on every run (not
    cached) so editing a threshold and re-running immediately picks up
    the change."""
    import strategies as strategies_package
    path = Path(strategies_package.__path__[0]) / f"{strategy_name}.json"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def required_dynamic_indicators(strategy_name: str) -> List[IndicatorSpec]:
    """Every dynamically-computed indicator (core/domain/
    indicator_registry.py) strategy_name's conditions.json declares
    beyond the always-available fixed set — what run_backtest()'s
    extra_indicators needs so those references resolve to real values
    instead of a permanent None. [] for a strategy with no conditions.json
    yet, or one that only uses bare/fixed field references."""
    return required_indicators_from_json(read_strategy_params_json(strategy_name))


def breakdown_rows(trades: List[Trade], key_fn: Callable[[Trade], Optional[str]]) -> List[dict]:
    """Same shape as server/main.py's by_strategy: [{strategy_name,
    deployment_id, capital, metrics}] — `strategy_name` here holds
    whatever's being broken down by (symbol/market condition/side), so
    the frontend can reuse StrategyTable unmodified for all three. Shared
    between backtest_server.py (the UI's /api/backtest/run) and
    run_backtest.py (the CLI) so a stored result's shape can never drift
    apart depending on which one produced it — a real bug once: the CLI's
    saved by_symbol/by_market_condition/by_side were simply missing,
    which crashed the Analysis tab (StrategyTable expects them) for every
    result the CLI had ever saved."""
    groups: Dict[str, List[Trade]] = {}
    for t in trades:
        key = key_fn(t)
        if key is not None:
            groups.setdefault(key, []).append(t)

    rows = [
        {
            "strategy_name": key,
            "deployment_id": None,
            "capital": 0,
            "metrics": asdict(compute_performance_metrics(group, capital=0)),
        }
        for key, group in groups.items()
    ]
    return sorted(rows, key=lambda r: r["metrics"]["total_trades"], reverse=True)


def oi_level_breakdown_rows(trades: List[Trade]) -> List[dict]:
    """Low/Medium/High OI tercile breakdown of trades that have an
    entry_oi (stock options only — see core/domain/models.py::
    Trade.entry_oi). Cutoffs are computed from THIS result's own trades,
    not a fixed absolute threshold — OI magnitude isn't comparable across
    contracts (a strike with 50,000 OI might be "high" for one underlying
    and "low" for another with naturally larger open interest), so a
    global threshold would misclassify most results. Trades with
    entry_oi=None (equity, index options, pre-existing trades) are
    excluded entirely rather than forming their own group. [] when fewer
    than 3 trades have an entry_oi (not enough to form 3 groups)."""
    oi_values = sorted(t.entry_oi for t in trades if t.entry_oi is not None)
    if len(oi_values) < 3:
        return []
    n = len(oi_values)
    low_cutoff = oi_values[n // 3]
    high_cutoff = oi_values[(2 * n) // 3]

    def _level(t: Trade) -> Optional[str]:
        if t.entry_oi is None:
            return None
        if t.entry_oi <= low_cutoff:
            return "Low OI"
        if t.entry_oi <= high_cutoff:
            return "Medium OI"
        return "High OI"

    return breakdown_rows(trades, _level)


def symbols_identity(symbols: Optional[List[str]], is_full_watchlist: bool) -> str:
    """Canonical form of "what symbols were requested" for dedup identity —
    sorted so order never matters, and a distinct sentinel for "whole
    watchlist" so that stays its own identity even as watchlist membership
    changes over time."""
    if is_full_watchlist or not symbols:
        return "WATCHLIST"
    return ",".join(sorted(s.upper() for s in symbols))


def save_backtest_result(
    result_repo: IBacktestResultRepository,
    strategy_name: str,
    symbols_id: str,
    config: StrategyConfig,
    charges_enabled: bool,
    date_from: dt.date,
    date_to: dt.date,
    result: Dict[str, Any],
    strategy_params_json: Optional[str] = None,
) -> BacktestResult:
    params = BacktestRunParams(
        strategy_name=strategy_name,
        symbols=symbols_id,
        timeframe=config.timeframe,
        date_from=date_from,
        date_to=date_to,
        quantity=config.quantity,
        stoploss_pct=config.stoploss_pct,
        target_pct=config.target_pct,
        trailing_pct=config.trailing_pct,
        max_cycles_per_day=config.max_cycles_per_day,
        start_time=config.start_time,
        end_time=config.end_time,
        charges_enabled=charges_enabled,
        strategy_params_json=(
            strategy_params_json if strategy_params_json is not None
            else read_strategy_params_json(strategy_name)
        ),
    )
    return result_repo.save_result(params, result)


def save_per_symbol_results(
    result_repo: IBacktestResultRepository,
    strategy_name: str,
    symbols_used: List[str],
    all_trades: List[Trade],
    config: StrategyConfig,
    charges_enabled: bool,
    date_from: dt.date,
    date_to: dt.date,
    capital: float,
    strategy_params_json: Optional[str] = None,
) -> Dict[str, BacktestResult]:
    """Splits a multi-symbol run's trades by symbol and persists EACH
    symbol as its own stored result (symbols_id = that one symbol, not a
    joined list or the "WATCHLIST" sentinel) — replaces saving one
    combined row per run/scenario. This is what lets the Analysis tab
    filter/sort by individual symbol without opening a combined result's
    "By Symbol" table every time, and makes dedup correctly per-symbol:
    adding one new symbol to a watchlist and re-running only computes
    that new symbol, since every other symbol's identity already matches
    a stored row (see _find_already_tested in batch_job_runner.py).

    symbols_used is passed explicitly (not derived from all_trades) so a
    symbol that was tested but produced zero trades still gets its own
    row — "never triggers with these params" is itself the answer to
    "was this stock any good," not something to silently omit.

    The combined "whole watchlist together" view (one equity curve/Sharpe/
    drawdown across every symbol) is deliberately NOT persisted here —
    those numbers depend on trades' time-ordering across symbols, so they
    can't be validly reconstructed later from separately-stored per-symbol
    aggregates. Callers needing that view recompute it live (same cost as
    the original run) rather than trusting a stored approximation.
    """
    trades_by_symbol: Dict[str, List[Trade]] = {s: [] for s in symbols_used}
    for t in all_trades:
        trades_by_symbol.setdefault(t.symbol, []).append(t)

    saved: Dict[str, BacktestResult] = {}
    for symbol, trades in trades_by_symbol.items():
        metrics = compute_performance_metrics(trades, capital)
        result = {
            "symbols_used": [symbol],
            "symbols_missing_data": [],
            "total_trades": len(trades),
            "metrics": asdict(metrics),
            "equity_curve": [asdict(p) for p in equity_curve(trades)],
            "by_symbol": breakdown_rows(trades, lambda t: t.symbol),
            "by_market_condition": breakdown_rows(trades, lambda t: t.market_condition),
            "by_side": breakdown_rows(trades, lambda t: t.side.value),
            "by_oi_level": oi_level_breakdown_rows(trades),
            "capital": capital,
        }
        saved[symbol] = save_backtest_result(
            result_repo,
            strategy_name=strategy_name,
            symbols_id=symbol,
            config=config,
            charges_enabled=charges_enabled,
            date_from=date_from,
            date_to=date_to,
            result=result,
            strategy_params_json=strategy_params_json,
        )
    return saved
