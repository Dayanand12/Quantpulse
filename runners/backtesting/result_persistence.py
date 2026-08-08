# runners/backtesting/result_persistence.py
"""Shared helper for logging a finished backtest run to backtest_results
(core/domain/backtest_result.py) — used by both backtest_server.py (the
UI's /api/backtest/run) and run_backtest.py (the CLI), so a run through
either path dedups against the same stored history.
"""

import datetime as dt
from typing import Any, Dict, List, Optional

from core.application.interfaces.backtest_result_repository import IBacktestResultRepository
from core.domain.backtest_result import BacktestResult, BacktestRunParams
from core.domain.models import StrategyConfig


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
    )
    return result_repo.save_result(params, result)
