# backtest_server.py
"""Standalone API for the backtesting UI (Backtest page in the frontend).

Deliberately separate from server/main.py's live-trading app: that app's
startup (run_live.py::main()) requires a working Zerodha broker session
before it'll even construct — backtesting only reads historical CSVs and
the watchlist DB table, neither of which needs a live broker connection.
Keeping this standalone means you can research/tune strategies without
having Zerodha logged in at all.

Runs on its own port (run_backtest_server.py, default 5050) — the
frontend's Vite dev proxy (frontend/vite.config.ts) routes /api/backtest/*
here and everything else to the main app on 5000, so from the browser's
perspective it's all one origin.
"""

import datetime as dt
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import strategies as strategies_package
from core.application.interfaces.backtest_result_repository import IBacktestResultRepository
from core.domain.backtest_result import BacktestResult
from core.domain.charges import ChargeConfig
from core.domain.metrics import compute_performance_metrics, equity_curve
from core.domain.models import StrategyConfig, Trade
from core.exceptions import ValidationError, register_exception_handlers
from infrastructure.config.settings import get_settings
from infrastructure.persistence.database import create_session_factory
from infrastructure.persistence.sql_backtest_result_repository import SqlBacktestResultRepository
from infrastructure.strategies.filesystem_strategy_source_repository import (
    FilesystemStrategySourceRepository,
)
from runners.backtesting.engine import run_backtest
from runners.backtesting.historical_loader import load_equity_csv
from runners.backtesting.result_persistence import save_backtest_result, symbols_identity
from runners.backtesting.strategy_cloner import clone_strategy
from runners.backtesting.strategy_resolver import (
    UnknownStrategyError,
    list_strategy_names,
    resolve_strategy_class,
)
from runners.backtesting.watchlist import get_tradeable_watchlist_symbols


def _default_csv_path(symbol: str) -> str:
    return os.path.join(get_settings().historical_data_dir, f"{symbol}_historical.csv")


# Trades returned to the browser are capped — a full watchlist run can
# produce thousands (e.g. 9,479 for an unfiltered vwap_reclaim sweep);
# metrics/breakdowns below are always computed over the COMPLETE set
# regardless of this cap, only the raw trade-log table is limited, most
# recent first, so the UI stays responsive.
MAX_TRADES_RETURNED = 2000

HHMM_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class CloneStrategyRequest(BaseModel):
    base_strategy: str
    new_name: str


class BacktestRunRequest(BaseModel):
    strategy: str
    symbols: Optional[List[str]] = None  # None/empty -> full watchlist
    timeframe: str = "minute"
    quantity: int = Field(50, gt=0)
    stoploss_pct: float = Field(0.8, gt=0)
    target_pct: float = Field(2.0, gt=0)
    trailing_pct: float = Field(0.1, gt=0)
    max_cycles_per_day: int = Field(10, gt=0)
    start_time: str = Field("09:20", pattern=HHMM_PATTERN)
    end_time: str = Field("11:30", pattern=HHMM_PATTERN)
    capital: float = Field(100_000, gt=0)
    charges: bool = True
    # "YYYY-MM-DD"; None on either end -> that side is unbounded (as much
    # history as the CSV has). Indicators are still warmed up over the
    # FULL series regardless — see engine.run_backtest's docstring.
    date_from: Optional[str] = None
    date_to: Optional[str] = None


def _parse_date(value: Optional[str]) -> Optional[dt.date]:
    return dt.date.fromisoformat(value) if value else None


def _result_summary(r: BacktestResult) -> dict:
    m = r.result.get("metrics", {})
    p = r.params
    return {
        "id": r.id,
        "strategy_name": p.strategy_name,
        "symbols": p.symbols,
        "timeframe": p.timeframe,
        "date_from": p.date_from.isoformat(),
        "date_to": p.date_to.isoformat(),
        "quantity": p.quantity,
        "stoploss_pct": p.stoploss_pct,
        "target_pct": p.target_pct,
        "trailing_pct": p.trailing_pct,
        "max_cycles_per_day": p.max_cycles_per_day,
        "start_time": p.start_time,
        "end_time": p.end_time,
        "charges_enabled": p.charges_enabled,
        "total_trades": m.get("total_trades", 0),
        "win_rate": m.get("win_rate"),
        "profit_factor": m.get("profit_factor"),
        "total_pnl": m.get("total_pnl"),
        "sharpe_ratio": m.get("sharpe_ratio"),
        "max_drawdown_pct": m.get("max_drawdown_pct"),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _result_detail(r: BacktestResult) -> dict:
    return {"summary": _result_summary(r), "result": r.result}


def _trade_to_dict(t: Trade) -> dict:
    return {
        "symbol": t.symbol,
        "side": t.side.value,
        "closed_at": t.closed_at.isoformat(),
        "entry": t.entry_price,
        "exit": t.exit_price,
        "qty": t.quantity,
        "pnl": t.pnl,
        "charges": t.charges,
        "net_pnl": t.net_pnl,
        "market_condition": t.market_condition,
    }


def _breakdown_rows(trades: List[Trade], key_fn) -> List[dict]:
    """Same shape as server/main.py's by_strategy: [{strategy_name,
    deployment_id, capital, metrics}] — `strategy_name` here holds
    whatever's being broken down by (symbol/market condition/side), so
    the frontend can reuse StrategyTable unmodified for all three."""
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


def create_app() -> FastAPI:
    app = FastAPI(title="QuantPulse Backtest API")
    settings = get_settings()
    source_repo = FilesystemStrategySourceRepository(Path(strategies_package.__path__[0]))
    session_factory = create_session_factory(settings.database_url)
    result_repo: IBacktestResultRepository = SqlBacktestResultRepository(session_factory)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    @app.get("/api/backtest/strategies")
    def list_strategies():
        names = list_strategy_names()
        result = []
        for name in names:
            try:
                cls = resolve_strategy_class(name)
                instance = cls()
                result.append({
                    "name": instance.name,
                    "display_name": instance.display_name,
                    "side": instance.side.value,
                })
            except Exception:
                continue  # a broken/WIP strategy file shouldn't take the whole list down
        return result

    @app.get("/api/backtest/watchlist")
    def watchlist():
        return {"symbols": get_tradeable_watchlist_symbols()}

    @app.post("/api/backtest/strategies/clone")
    def clone(body: CloneStrategyRequest):
        try:
            resolve_strategy_class(body.base_strategy)
        except UnknownStrategyError as e:
            raise ValidationError(str(e))

        clone_strategy(source_repo, body.base_strategy, body.new_name)

        cls = resolve_strategy_class(body.new_name)
        instance = cls()
        return {"name": instance.name, "display_name": instance.display_name, "side": instance.side.value}

    @app.post("/api/backtest/run")
    def run(body: BacktestRunRequest):
        try:
            strategy_cls = resolve_strategy_class(body.strategy)
        except UnknownStrategyError as e:
            raise ValidationError(str(e))

        symbols = body.symbols or get_tradeable_watchlist_symbols()
        if not symbols:
            raise ValidationError("No symbols to backtest (empty watchlist and none given).")

        config = StrategyConfig(
            quantity=body.quantity,
            stoploss_pct=body.stoploss_pct,
            target_pct=body.target_pct,
            trailing_pct=body.trailing_pct,
            max_cycles_per_day=body.max_cycles_per_day,
            start_time=body.start_time,
            end_time=body.end_time,
            timeframe=body.timeframe,
        )
        charge_config = ChargeConfig() if body.charges else None
        requested_date_from = _parse_date(body.date_from)
        requested_date_to = _parse_date(body.date_to)

        all_trades: List[Trade] = []
        symbols_used = []
        symbols_missing_data = []
        # Tracks how much history was actually available, so a run with no
        # explicit date_from/date_to still gets a concrete identity below
        # (see BacktestRunParams — NULL date bounds would let SQLite treat
        # every unbounded run as distinct, defeating dedup entirely).
        data_min_date: Optional[dt.date] = None
        data_max_date: Optional[dt.date] = None

        for symbol in symbols:
            csv_path = _default_csv_path(symbol)
            try:
                df = load_equity_csv(csv_path)
            except FileNotFoundError:
                symbols_missing_data.append(symbol)
                continue

            df_min = df["date"].min().date()
            df_max = df["date"].max().date()
            data_min_date = df_min if data_min_date is None else min(data_min_date, df_min)
            data_max_date = df_max if data_max_date is None else max(data_max_date, df_max)

            strategy = strategy_cls()  # fresh instance per symbol — no carried-over state
            trades = run_backtest(
                strategy, symbol, df, config, charge_config=charge_config,
                date_from=requested_date_from, date_to=requested_date_to,
            )
            all_trades.extend(trades)
            symbols_used.append(symbol)

        if not symbols_used:
            raise ValidationError(
                f"No historical data found for any requested symbol. Missing: {', '.join(symbols_missing_data)}"
            )

        metrics = compute_performance_metrics(all_trades, body.capital)
        sorted_trades = sorted(all_trades, key=lambda t: t.closed_at, reverse=True)

        response: Dict[str, Any] = {
            "symbols_used": symbols_used,
            "symbols_missing_data": symbols_missing_data,
            "total_trades": len(all_trades),
            "trades": [_trade_to_dict(t) for t in sorted_trades[:MAX_TRADES_RETURNED]],
            "trades_truncated": len(all_trades) > MAX_TRADES_RETURNED,
            "metrics": asdict(metrics),
            "equity_curve": [asdict(p) for p in equity_curve(all_trades)],
            "by_symbol": _breakdown_rows(all_trades, lambda t: t.symbol),
            "by_market_condition": _breakdown_rows(all_trades, lambda t: t.market_condition),
            "by_side": _breakdown_rows(all_trades, lambda t: t.side.value),
        }

        # Log this run to backtest_results — same numbers as `response`
        # minus the raw trade log (cheap to regenerate by re-running these
        # exact params; not worth the row size for a stored history whose
        # whole point is being cheap to scan across many runs).
        stored_result = {k: v for k, v in response.items() if k not in ("trades", "trades_truncated")}
        stored_result["capital"] = body.capital
        saved = save_backtest_result(
            result_repo,
            strategy_name=body.strategy,
            symbols_id=symbols_identity(body.symbols, is_full_watchlist=not body.symbols),
            config=config,
            charges_enabled=body.charges,
            date_from=requested_date_from or data_min_date,
            date_to=requested_date_to or data_max_date,
            result=stored_result,
        )
        response["saved_result_id"] = saved.id

        return response

    @app.get("/api/backtest/results")
    def list_results(strategy: str):
        return [_result_summary(r) for r in result_repo.list_results(strategy)]

    @app.get("/api/backtest/results/{result_id}")
    def get_result(result_id: int):
        r = result_repo.get_result(result_id)
        if r is None:
            raise ValidationError(f"No stored backtest result with id {result_id}")
        return _result_detail(r)

    return app


app = create_app()
