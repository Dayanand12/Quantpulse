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
import json
import os
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

import strategies as strategies_package
from core.application.interfaces.backtest_result_repository import IBacktestResultRepository
from core.application.interfaces.batch_job_repository import IBatchJobRepository
from core.domain.backtest_result import BacktestResult
from core.domain.batch_job import BatchJob
from core.domain.charges import ChargeConfig
from core.domain.metrics import compute_performance_metrics, equity_curve
from core.domain.models import StrategyConfig, Trade
from core.exceptions import ValidationError, register_exception_handlers
from infrastructure.config.settings import get_settings
from infrastructure.persistence.database import create_session_factory
from infrastructure.persistence.sql_backtest_result_repository import SqlBacktestResultRepository
from infrastructure.persistence.sql_batch_job_repository import SqlBatchJobRepository
from infrastructure.persistence.sql_deployment_repository import SqlDeploymentRepository
from infrastructure.strategies.filesystem_strategy_params_repository import (
    FilesystemStrategyParamsRepository,
)
from infrastructure.strategies.filesystem_strategy_source_repository import (
    FilesystemStrategySourceRepository,
)
from runners.backtesting.batch_job_import import parse_scenarios_from_excel
from runners.backtesting.batch_job_runner import run_batch_job
from runners.backtesting.batch_runner import PanelSpec, run_batch_backtests
from runners.backtesting.engine import run_backtest
from runners.backtesting.historical_loader import load_equity_csv
from runners.backtesting.report import build_blank_scenario_template, export_stored_results_to_excel
from runners.backtesting.result_persistence import (
    breakdown_rows,
    read_strategy_params_json,
    required_dynamic_indicators,
    save_backtest_result,
    symbols_identity,
)
from runners.backtesting.strategy_cloner import clone_strategy
from runners.backtesting.strategy_resolver import (
    UnknownStrategyError,
    list_strategy_names,
    resolve_strategy_class,
)
from runners.backtesting.telegram_bot import run_telegram_bot_forever
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


class SaveStrategyParamsRequest(BaseModel):
    raw_json: str


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


class BatchPanelRequest(BaseModel):
    label: str = ""
    # {parameter_name: value} merged into the strategy's conditions.json
    # "parameters" block for this panel only — never written to disk (see
    # runners/backtesting/batch_runner.py). Empty dict runs the strategy's
    # saved parameters unchanged.
    overrides: Dict[str, float] = Field(default_factory=dict)


class BatchRunRequest(BaseModel):
    """The "6 panels" feature: one strategy, run against several parameter
    sets in one request (user: "there will be 1 strategy and i will change
    parameters, not multiple strategies"). Every other field below is
    shared across all panels — same symbols/dates/risk config, only
    `panels[i].overrides` differs between runs."""

    strategy: str
    panels: List[BatchPanelRequest] = Field(..., min_length=1, max_length=6)
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
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    save: bool = True


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
        # "" for a strategy not migrated to condition-JSON yet (e.g.
        # orb_reversal) — see core/domain/strategy_conditions.py. Lets the
        # Analysis tab show/compare which indicator thresholds a given
        # stored run actually used, not just its risk/sizing settings.
        "strategy_params_json": p.strategy_params_json,
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


def _batch_job_to_dict(job: BatchJob) -> dict:
    return {
        "id": job.id,
        "strategy_name": job.strategy_name,
        "status": job.status,
        "shared_config": job.shared_config,
        "total_scenarios": job.total_scenarios,
        "processed_scenarios": job.processed_scenarios,
        "scenarios": [
            {
                "label": s.label,
                "overrides": s.overrides,
                "config_overrides": s.config_overrides,
                "status": s.status,
                "saved_result_id": s.saved_result_id,
                "error": s.error,
            }
            for s in job.scenarios
        ],
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


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


def create_app() -> FastAPI:
    settings = get_settings()
    source_repo = FilesystemStrategySourceRepository(Path(strategies_package.__path__[0]))
    params_repo = FilesystemStrategyParamsRepository(Path(strategies_package.__path__[0]))
    session_factory = create_session_factory(settings.database_url)
    result_repo: IBacktestResultRepository = SqlBacktestResultRepository(session_factory)
    # Only wraps a session_factory (thread-safe to call repeatedly) — safe
    # to hand to a background thread (runners/backtesting/
    # batch_job_runner.py) since each repository method opens its own
    # fresh session per call rather than sharing one across threads.
    job_repo: IBatchJobRepository = SqlBatchJobRepository(session_factory)
    # Read-only here — only used to block deleting a strategy that's
    # currently wired to a deployment (live or paper), never to write.
    deployment_repo = SqlDeploymentRepository(session_factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Opt-in: only starts if TELEGRAM_BOT_TOKEN is set (see
        # infrastructure/config/settings.py). Daemon thread — dies with
        # the process, no explicit shutdown needed on the way out.
        if settings.telegram_bot_token:
            threading.Thread(
                target=run_telegram_bot_forever,
                args=(settings.telegram_bot_token, settings.telegram_allowed_user_id, job_repo, result_repo),
                daemon=True,
            ).start()
        yield

    app = FastAPI(title="QuantPulse Backtest API", lifespan=lifespan)

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

        clone_strategy(source_repo, body.base_strategy, body.new_name, params_repo=params_repo)

        cls = resolve_strategy_class(body.new_name)
        instance = cls()
        return {"name": instance.name, "display_name": instance.display_name, "side": instance.side.value}

    @app.get("/api/backtest/strategies/{name}/params")
    def get_strategy_params(name: str):
        raw = params_repo.get_params(name)
        return {"has_params": raw is not None, "raw_json": raw}

    @app.put("/api/backtest/strategies/{name}/params")
    def save_strategy_params(name: str, body: SaveStrategyParamsRequest):
        params_repo.save_params(name, body.raw_json)
        return {"raw_json": body.raw_json}

    @app.delete("/api/backtest/strategies/{name}")
    def delete_strategy(name: str):
        deployed_by = [d.id for d in deployment_repo.list_deployments() if d.strategy_name == name]
        if deployed_by:
            raise ValidationError(
                f"Can't delete {name!r} — it's used by {len(deployed_by)} deployment(s) "
                f"(disable/remove those on the Strategies page first)."
            )

        source_repo.delete_source(name)
        params_repo.delete_params(name)  # no-op if this strategy never had a params file
        return {"deleted": name}

    @app.delete("/api/backtest/results/{result_id}")
    def delete_result(result_id: int):
        result_repo.delete_result(result_id)
        return {"deleted": result_id}

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
        extra_indicators = required_dynamic_indicators(body.strategy)

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
                extra_indicators=extra_indicators,
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
            "by_symbol": breakdown_rows(all_trades, lambda t: t.symbol),
            "by_market_condition": breakdown_rows(all_trades, lambda t: t.market_condition),
            "by_side": breakdown_rows(all_trades, lambda t: t.side.value),
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

    @app.post("/api/backtest/run-batch")
    def run_batch(body: BatchRunRequest):
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

        panel_specs = [
            PanelSpec(label=p.label or f"Panel {i + 1}", overrides=p.overrides)
            for i, p in enumerate(body.panels)
        ]
        symbol_csv_pairs = [(s, _default_csv_path(s)) for s in symbols]

        try:
            panel_results, symbols_used, symbols_missing_data = run_batch_backtests(
                strategy_cls, body.strategy, panel_specs, symbol_csv_pairs, config,
                charge_config=charge_config, date_from=requested_date_from, date_to=requested_date_to,
            )
        except ValueError as e:
            raise ValidationError(str(e))

        if not symbols_used:
            raise ValidationError(
                f"No historical data found for any requested symbol. Missing: {', '.join(symbols_missing_data)}"
            )

        # Same reasoning as run()'s data_min_date/data_max_date: an
        # unbounded date range still needs a concrete identity for dedup
        # (BacktestRunParams). Resolved once here (shared across panels),
        # not inside batch_runner.py's workers, since it's a property of
        # the symbol's data, not of any one panel's parameters.
        data_min_date: Optional[dt.date] = None
        data_max_date: Optional[dt.date] = None
        for symbol in symbols_used:
            df = load_equity_csv(_default_csv_path(symbol))
            df_min = df["date"].min().date()
            df_max = df["date"].max().date()
            data_min_date = df_min if data_min_date is None else min(data_min_date, df_min)
            data_max_date = df_max if data_max_date is None else max(data_max_date, df_max)

        symbols_id = symbols_identity(body.symbols, is_full_watchlist=not body.symbols)

        panels_response: List[Dict[str, Any]] = []
        for panel in panel_results:
            metrics = compute_performance_metrics(panel.trades, body.capital)
            panel_response: Dict[str, Any] = {
                "label": panel.label,
                "overrides": panel.overrides,
                "strategy_params_json": panel.strategy_params_json,
                "total_trades": len(panel.trades),
                "metrics": asdict(metrics),
                "equity_curve": [asdict(p) for p in equity_curve(panel.trades)],
                "by_symbol": breakdown_rows(panel.trades, lambda t: t.symbol),
                "by_market_condition": breakdown_rows(panel.trades, lambda t: t.market_condition),
                "by_side": breakdown_rows(panel.trades, lambda t: t.side.value),
            }

            if body.save:
                stored_result = {k: v for k, v in panel_response.items() if k not in ("label", "overrides")}
                stored_result["capital"] = body.capital
                stored_result["symbols_used"] = symbols_used
                stored_result["symbols_missing_data"] = symbols_missing_data
                saved = save_backtest_result(
                    result_repo,
                    strategy_name=body.strategy,
                    symbols_id=symbols_id,
                    config=config,
                    charges_enabled=body.charges,
                    date_from=requested_date_from or data_min_date,
                    date_to=requested_date_to or data_max_date,
                    result=stored_result,
                    strategy_params_json=panel.strategy_params_json,
                )
                panel_response["saved_result_id"] = saved.id

            panels_response.append(panel_response)

        return {
            "symbols_used": symbols_used,
            "symbols_missing_data": symbols_missing_data,
            "panels": panels_response,
        }

    @app.post("/api/backtest/batch-jobs")
    async def create_batch_job(
        strategy: str = Form(...),
        symbols: Optional[str] = Form(None),  # comma-separated; empty/omitted -> full watchlist
        timeframe: str = Form("minute"),
        quantity: int = Form(50),
        stoploss_pct: float = Form(0.8),
        target_pct: float = Form(2.0),
        trailing_pct: float = Form(0.1),
        max_cycles_per_day: int = Form(10),
        start_time: str = Form("09:20"),
        end_time: str = Form("11:30"),
        capital: float = Form(100_000),
        charges: bool = Form(True),
        date_from: Optional[str] = Form(None),
        date_to: Optional[str] = Form(None),
        file: UploadFile = File(...),
    ):
        """The bulk-upload feature: an Excel of parameter scenarios,
        processed in the background (runners/backtesting/
        batch_job_runner.py) — the response comes back the moment parsing
        + validation finishes, well before any backtest has actually run,
        so a typo'd column surfaces in seconds. Unlike /run-batch, this
        never blocks on the backtests themselves and has no panel-count
        cap."""
        try:
            strategy_cls = resolve_strategy_class(strategy)
        except UnknownStrategyError as e:
            raise ValidationError(str(e))

        raw_params_json = read_strategy_params_json(strategy)
        if not raw_params_json:
            raise ValidationError(
                f"{strategy!r} has no conditions.json — bulk parameter scenarios need one."
            )
        valid_parameter_names = set(json.loads(raw_params_json).get("parameters", {}).keys())

        content = await file.read()
        try:
            scenarios = parse_scenarios_from_excel(content, valid_parameter_names)
        except Exception as e:
            raise ValidationError(f"Couldn't read that file as an Excel workbook: {e}")

        if not scenarios:
            raise ValidationError(
                "No scenarios found in that file — check it has a header row plus at least one data row."
            )

        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None
        resolved_symbols = symbol_list or get_tradeable_watchlist_symbols()
        if not resolved_symbols:
            raise ValidationError("No symbols to backtest (empty watchlist and none given).")

        shared_config = {
            "symbols": symbol_list,
            "timeframe": timeframe,
            "quantity": quantity,
            "stoploss_pct": stoploss_pct,
            "target_pct": target_pct,
            "trailing_pct": trailing_pct,
            "max_cycles_per_day": max_cycles_per_day,
            "start_time": start_time,
            "end_time": end_time,
            "capital": capital,
            "charges": charges,
            "date_from": date_from,
            "date_to": date_to,
        }
        job = job_repo.create(BatchJob(strategy_name=strategy, shared_config=shared_config, scenarios=scenarios))

        symbol_csv_pairs = [(s, _default_csv_path(s)) for s in resolved_symbols]
        symbols_id = symbols_identity(symbol_list, is_full_watchlist=not symbol_list)

        # Detached from this request on purpose — the thread outlives the
        # HTTP response, so closing the browser (or the laptop) doesn't
        # stop it. Only the backtest_server.py process itself needs to
        # keep running. Risk/sizing settings are resolved PER SCENARIO
        # inside run_batch_job from job.shared_config + each scenario's
        # own config_overrides, not passed in from here — see
        # runners/backtesting/batch_job_runner.py.
        thread = threading.Thread(
            target=run_batch_job,
            args=(job, strategy_cls, symbol_csv_pairs, symbols_id, job_repo, result_repo),
            daemon=True,
        )
        thread.start()

        return _batch_job_to_dict(job)

    # Declared before /api/backtest/batch-jobs/{job_id} — same reasoning
    # as /api/backtest/results/export above: Starlette matches routes in
    # declaration order, so "template" would otherwise be swallowed by
    # {job_id}'s int path converter and 422 instead of reaching here.
    @app.get("/api/backtest/batch-jobs/template")
    def batch_job_template(strategy: str):
        try:
            resolve_strategy_class(strategy)
        except UnknownStrategyError as e:
            raise ValidationError(str(e))

        raw_params_json = read_strategy_params_json(strategy)
        if not raw_params_json:
            raise ValidationError(
                f"{strategy!r} has no conditions.json — bulk parameter scenarios need one."
            )
        parameter_defaults = json.loads(raw_params_json).get("parameters", {})

        content = build_blank_scenario_template(parameter_defaults)
        filename = f"{strategy}_scenario_template.xlsx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/backtest/batch-jobs/{job_id}")
    def get_batch_job(job_id: int):
        job = job_repo.get(job_id)
        if job is None:
            raise ValidationError(f"No batch job with id {job_id}")
        return _batch_job_to_dict(job)

    @app.get("/api/backtest/batch-jobs")
    def list_batch_jobs(strategy: str):
        return [_batch_job_to_dict(j) for j in job_repo.list_for_strategy(strategy)]

    @app.get("/api/backtest/results")
    def list_results(strategy: str):
        return [_result_summary(r) for r in result_repo.list_results(strategy)]

    # Declared before /api/backtest/results/{result_id} — Starlette matches
    # routes in declaration order, so "export" would otherwise be swallowed
    # by {result_id}'s int path converter and 422 instead of reaching here.
    @app.get("/api/backtest/results/export")
    def export_results(strategy: str):
        results = result_repo.list_results(strategy)
        if not results:
            raise ValidationError(f"No stored backtest results for strategy {strategy!r}")

        content = export_stored_results_to_excel(results)
        filename = f"{strategy}_backtest_comparison.xlsx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/backtest/results/{result_id}")
    def get_result(result_id: int):
        r = result_repo.get_result(result_id)
        if r is None:
            raise ValidationError(f"No stored backtest result with id {result_id}")
        return _result_detail(r)

    return app


app = create_app()
