# runners/backtesting/result_persistence.py
"""Shared helper for logging a finished backtest run to backtest_results
(core/domain/backtest_result.py) — used by both backtest_server.py (the
UI's /api/backtest/run) and run_backtest.py (the CLI), so a run through
either path dedups against the same stored history.
"""

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.application.interfaces.backtest_result_repository import IBacktestResultRepository
from core.domain.backtest_result import BacktestResult, BacktestRunParams
from core.domain.indicator_registry import IndicatorSpec
from core.domain.models import StrategyConfig
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
