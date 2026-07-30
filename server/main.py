# server/main.py
"""FastAPI API layer.

Depends only on core.container.Container — every route calls an interface
or iterates container.deployment_runtimes, never a concrete class. This is
what "business logic must never know whether requests come from Desktop/
Web/Mobile/REST/WebSocket" means in practice: swap this file for a CLI or
a desktop app's request handler and the container underneath doesn't
change at all.
"""

import asyncio
import datetime as dt
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.state_store import stage_results
from backend.eod_report import generate_eod_report
from backend.market_analysis_engine import MarketAnalysisEngine
from backend.report_generator import generate_report
from core.application.interfaces.trade_repository import TradeFilter
from core.container import Container
from core.domain.metrics import (
    compute_performance_metrics,
    drawdown_series,
    equity_curve,
    pnl_by_period,
    profit_distribution,
    rolling_sharpe,
)
from core.domain.models import Deployment, StrategyConfig
from core.exceptions import NotFoundError, ValidationError, register_exception_handlers
from infrastructure.config.settings import Settings
from live.live_engine import SUPPORTED_TIMEFRAMES
from server.serializers import position_to_dict, snapshot_map_to_dict, trade_to_dict
from server.ws_manager import ConnectionManager


class WatchlistUpdateRequest(BaseModel):
    symbols: List[str]


class StrategySourceCreateRequest(BaseModel):
    name: str
    source: str


class StrategySourceUpdateRequest(BaseModel):
    source: str


HHMM_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class DeploymentRequest(BaseModel):
    strategy_name: str
    symbols: List[str]
    capital: float = Field(gt=0)
    quantity: int = Field(gt=0)
    stoploss_pct: float = Field(gt=0)
    target_pct: float = Field(gt=0)
    trailing_pct: float = Field(gt=0)
    max_cycles_per_day: int = Field(gt=0)
    enabled: bool = True
    start_time: str = Field(default="09:20", pattern=HHMM_PATTERN)
    end_time: str = Field(default="11:30", pattern=HHMM_PATTERN)
    timeframe: str = "minute"


def _deployment_to_dict(deployment: Deployment) -> dict:
    return {
        "id": deployment.id,
        "strategy_name": deployment.strategy_name,
        "symbols": list(deployment.symbols),
        "capital": deployment.capital,
        "quantity": deployment.config.quantity,
        "stoploss_pct": deployment.config.stoploss_pct,
        "target_pct": deployment.config.target_pct,
        "trailing_pct": deployment.config.trailing_pct,
        "max_cycles_per_day": deployment.config.max_cycles_per_day,
        "enabled": deployment.enabled,
        "start_time": deployment.config.start_time,
        "end_time": deployment.config.end_time,
        "timeframe": deployment.config.timeframe,
    }


def create_app(container: Container, settings: Settings) -> FastAPI:

    analysis_engine = MarketAnalysisEngine(container.zerodha_client)
    manager = ConnectionManager()

    def _validate_deployment_request(body: DeploymentRequest) -> List[str]:
        strategy_names = {s.name for s in container.strategy_registry.list_strategies()}
        if body.strategy_name not in strategy_names:
            raise ValidationError(f"Unknown strategy: {body.strategy_name}")

        cleaned = list(dict.fromkeys(s.strip().upper() for s in body.symbols if s.strip()))
        if not cleaned:
            raise ValidationError("Deployment must include at least one symbol.")

        watchlist = set(container.watchlist_repository.get_symbols())
        unknown = [s for s in cleaned if s not in watchlist]
        if unknown:
            raise ValidationError(
                f"Symbols not in watchlist: {', '.join(unknown)}. "
                "Add them to the watchlist first."
            )

        if body.start_time >= body.end_time:
            raise ValidationError(
                f"start_time ({body.start_time}) must be before end_time ({body.end_time})."
            )

        if body.timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValidationError(
                f"Unknown timeframe: {body.timeframe}. Must be one of: "
                f"{', '.join(SUPPORTED_TIMEFRAMES)}."
            )

        _validate_capital_sufficiency(cleaned, body.quantity, body.capital)

        return cleaned

    def _validate_capital_sufficiency(symbols: List[str], quantity: int, capital: float) -> None:
        """Catches the exact mistake that cost hours of silent no-op paper
        trading earlier: a quantity that's simply too expensive for the
        capital at today's real price. Checked against whatever live tick
        is already available (no new data source) — a symbol with no tick
        yet is skipped rather than blocking on a data-availability gap."""
        ticks = container.market_data_provider.get_latest_ticks()
        problems = []

        for symbol in symbols:
            tick = ticks.get(symbol)
            if tick is None or not tick.ltp:
                continue

            required = quantity * tick.ltp
            if required > capital:
                max_qty = int(capital // tick.ltp)
                problems.append(
                    f"{symbol}: need ₹{required:,.0f} for {quantity} shares at "
                    f"₹{tick.ltp:,.2f}, but capital is only ₹{capital:,.0f}. Reduce "
                    f"quantity to {max_qty} or fewer, or increase capital to at least "
                    f"₹{required:,.0f}."
                )

        if problems:
            raise ValidationError(" ".join(problems))

    def build_positions_view():
        snapshot = container.trading_engine.get_snapshot()
        views = []

        for runtime in container.deployment_runtimes:
            for position in runtime.order_repository.get_open_positions():
                market = snapshot.get(position.symbol)
                ltp = market.ltp if market else None
                state = runtime.execution_manager.trade_state.get(position.symbol)

                pnl = None
                if ltp is not None:
                    pnl = (
                        (position.entry_price - ltp) * position.quantity
                        if position.side.value == "SELL"
                        else (ltp - position.entry_price) * position.quantity
                    )

                views.append({
                    "symbol": position.symbol,
                    "side": position.side.value,
                    "qty": position.quantity,
                    "entry": position.entry_price,
                    "ltp": ltp,
                    "stop_loss": state["stop_loss"] if state else None,
                    "target": state["target"] if state else None,
                    "unrealized_pnl": pnl,
                    "deployment_id": runtime.deployment.id,
                    "strategy_name": runtime.deployment.strategy_name,
                })

        return views

    def aggregate_broker_status() -> dict:
        """Sums every deployment's own capital pool into one view. Kept for
        the fields the frontend actually reads (available_capital,
        total_trades, trade_log) — open_positions is included for shape
        compatibility but the UI reads the richer build_positions_view()
        list instead, so a same-symbol-in-two-deployments collision here
        (last write wins) isn't user-visible today."""
        available_capital = 0.0
        total_trades = 0
        open_positions = {}
        trade_log = []

        for runtime in container.deployment_runtimes:
            status = runtime.portfolio_service.get_status()
            available_capital += status.available_capital
            total_trades += status.total_trades

            for position in status.open_positions:
                d = position_to_dict(position)
                d["deployment_id"] = runtime.deployment.id
                d["strategy_name"] = runtime.deployment.strategy_name
                open_positions[position.symbol] = d

            for trade in status.trade_log:
                d = trade_to_dict(trade)
                d["deployment_id"] = runtime.deployment.id
                d["strategy_name"] = runtime.deployment.strategy_name
                trade_log.append(d)

        return {
            "available_capital": available_capital,
            "open_positions": open_positions,
            "total_trades": total_trades,
            "trade_log": trade_log,
        }

    def build_market_ticker():
        ticks = container.market_data_provider.get_latest_ticks()
        result = {}

        for symbol in settings.market_ticker_symbols:
            tick = ticks.get(symbol)
            if tick is None:
                continue

            change = None
            change_pct = None
            if tick.prev_close:
                change = tick.ltp - tick.prev_close
                change_pct = (change / tick.prev_close) * 100

            result[symbol] = {
                "ltp": tick.ltp,
                "prev_close": tick.prev_close,
                "change": change,
                "change_pct": change_pct,
                "timestamp": tick.timestamp.isoformat(),
            }

        return result

    def build_full_snapshot() -> dict:
        """Every watchlist symbol, not just the ones LiveEngine has produced
        an indicator snapshot for. A freshly-added symbol (or one still
        waiting on its 25-candle warmup) has no MarketSnapshot yet, but its
        raw LTP is already flowing through market_data_provider — showing
        that lets the Screener page double as an "is this symbol's feed
        actually working" check instead of the row just not appearing."""
        indicator_snapshot = snapshot_map_to_dict(container.trading_engine.get_snapshot())
        ticks = container.market_data_provider.get_latest_ticks()

        result = dict(indicator_snapshot)
        for symbol in container.watchlist_repository.get_symbols():
            if symbol in result:
                continue
            tick = ticks.get(symbol)
            result[symbol] = {
                "ltp": tick.ltp if tick else None,
                "ema5": None,
                "ema9": None,
                "ema21": None,
                "rsi": None,
                "adx": None,
                "atr_pct": None,
                "vwap": None,
                "volume_ratio": None,
                "orb_low": None,
                "distance_to_or_low": None,
            }
        return result

    def build_live_payload():
        orb = stage_results.get("ORB", {})
        return {
            "snapshot": build_full_snapshot(),
            "stage_results": {
                "ORB": {
                    "stage1": orb.get("stage1", {}).get("stocks", []),
                    "stage2": orb.get("stage2", {}).get("stocks", []),
                    "stage3": orb.get("stage3", {}).get("stocks", []),
                }
            },
            "broker_status": aggregate_broker_status(),
            "positions": build_positions_view(),
            "market_ticker": build_market_ticker(),
        }

    async def broadcaster():
        while True:
            await manager.broadcast(build_live_payload())
            await asyncio.sleep(1)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(broadcaster())
        yield
        task.cancel()

    app = FastAPI(title="QuantPulse", lifespan=lifespan)
    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root():
        return {
            "service": "QuantPulse API",
            "ui": "python run_dev.py starts both backend and frontend; open http://localhost:5173",
            "docs": "/docs",
        }

    # -----------------------------
    # WebSocket: live push feed
    # -----------------------------
    @app.websocket("/ws/live")
    async def ws_live(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    # -----------------------------
    # REST: paper trading state (aggregated across all deployments)
    # -----------------------------
    @app.get("/api/live-status")
    def live_status():
        return aggregate_broker_status()

    @app.get("/api/positions")
    def positions():
        return build_positions_view()

    @app.get("/api/trades")
    def trades():
        return aggregate_broker_status()["trade_log"]

    # -----------------------------
    # REST: performance analytics (persisted trade history — survives
    # restarts and spans deleted deployments, unlike aggregate_broker_status
    # above which only reflects the current in-memory session). Every
    # number here comes from core/domain/metrics.py — this route only
    # filters, groups, and serializes; no metric math lives here.
    # -----------------------------
    @app.get("/api/analytics/summary")
    def analytics_summary(
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        timeframe: str = "daily",
    ):
        if timeframe not in ("daily", "weekly", "monthly"):
            raise ValidationError(f"Invalid timeframe: {timeframe}")

        all_trades = container.trade_repository.list_trades()
        available_strategies = sorted({t.strategy_name for t in all_trades if t.strategy_name})
        available_symbols = sorted({t.symbol for t in all_trades})

        trades = container.trade_repository.list_trades(
            TradeFilter(
                strategy_name=strategy or None,
                symbol=symbol or None,
                date_from=dt.date.fromisoformat(date_from) if date_from else None,
                date_to=dt.date.fromisoformat(date_to) if date_to else None,
            )
        )

        deployments = container.deployment_repository.list_deployments()
        if strategy:
            deployments = [d for d in deployments if d.strategy_name == strategy]

        trades_by_deployment: dict = {}
        for t in trades:
            trades_by_deployment.setdefault(t.deployment_id, []).append(t)

        by_strategy = []
        seen_ids = set()
        for deployment in deployments:
            seen_ids.add(deployment.id)
            deployment_trades = trades_by_deployment.get(deployment.id, [])
            by_strategy.append({
                "strategy_name": deployment.strategy_name,
                "deployment_id": deployment.id,
                "capital": deployment.capital,
                "metrics": asdict(compute_performance_metrics(deployment_trades, deployment.capital)),
            })

        # Trades tagged with a deployment that's since been deleted still
        # count towards "overall", and get their own row here — capital is
        # unknown for it, so %-of-capital metrics come back None. Mirrors
        # backend/eod_report.py's orphaned-deployment handling.
        for deployment_id, deployment_trades in trades_by_deployment.items():
            if deployment_id in seen_ids:
                continue
            strategy_name = deployment_trades[0].strategy_name or "Unknown strategy"
            by_strategy.append({
                "strategy_name": strategy_name,
                "deployment_id": deployment_id,
                "capital": 0,
                "metrics": asdict(compute_performance_metrics(deployment_trades, 0)),
            })

        total_capital = sum(d.capital for d in deployments)

        return {
            "overall": asdict(compute_performance_metrics(trades, total_capital)),
            "by_strategy": by_strategy,
            "equity_curve": [asdict(p) for p in equity_curve(trades, timeframe)],
            "pnl_by_period": [asdict(p) for p in pnl_by_period(trades, timeframe)],
            "drawdown": [asdict(p) for p in drawdown_series(trades, total_capital)],
            "profit_distribution": [asdict(b) for b in profit_distribution(trades)],
            "rolling_sharpe": [asdict(p) for p in rolling_sharpe(trades, total_capital)],
            "available_strategies": available_strategies,
            "available_symbols": available_symbols,
        }

    # -----------------------------
    # REST: strategies + deployments
    # -----------------------------
    @app.get("/api/strategies")
    def list_strategies():
        return [
            {"name": s.name, "display_name": s.display_name, "side": s.side.value}
            for s in container.strategy_registry.list_strategies()
        ]

    # -----------------------------
    # REST: strategy source (Strategy Builder tab)
    # -----------------------------
    @app.get("/api/strategy-source")
    def list_strategy_source():
        return container.strategy_source_repository.list_files()

    @app.get("/api/strategy-source/{name}")
    def get_strategy_source(name: str):
        return {"name": name, "source": container.strategy_source_repository.get_source(name)}

    @app.post("/api/strategy-source", status_code=201)
    def create_strategy_source(body: StrategySourceCreateRequest):
        container.strategy_source_repository.create_source(body.name, body.source)
        return {"name": body.name, "source": body.source}

    @app.put("/api/strategy-source/{name}")
    def update_strategy_source(name: str, body: StrategySourceUpdateRequest):
        container.strategy_source_repository.save_source(name, body.source)
        return {"name": name, "source": body.source}

    @app.get("/api/deployments")
    def list_deployments():
        runtimes_by_id = {r.deployment.id: r for r in container.deployment_runtimes}
        result = []

        for deployment in container.deployment_repository.list_deployments():
            entry = _deployment_to_dict(deployment)
            runtime = runtimes_by_id.get(deployment.id)
            entry["running"] = runtime is not None

            if runtime is not None:
                status = runtime.portfolio_service.get_status()
                metrics = compute_performance_metrics(
                    list(status.trade_log), deployment.capital
                )
                entry["status"] = {
                    "available_capital": status.available_capital,
                    "realized_pnl": status.realized_pnl,
                    "total_trades": status.total_trades,
                    "open_position_count": len(status.open_positions),
                    "win_rate": metrics.win_rate,
                    "profit_factor": metrics.profit_factor,
                    "gross_profit": metrics.gross_profit,
                    "gross_loss": metrics.gross_loss,
                    "max_drawdown": metrics.max_drawdown,
                    "max_drawdown_pct": metrics.max_drawdown_pct,
                    "avg_r_multiple": metrics.avg_r_multiple,
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "rejected_entries": [
                        {
                            "symbol": r.symbol,
                            "side": r.side.value,
                            "quantity": r.quantity,
                            "price": r.price,
                            "required_capital": r.required_capital,
                            "available_capital": r.available_capital,
                            "reason": r.reason,
                            "at": r.at.isoformat(),
                        }
                        for r in status.rejected_entries
                    ],
                }
            else:
                entry["status"] = None

            result.append(entry)

        return result

    @app.post("/api/deployments", status_code=201)
    def create_deployment(body: DeploymentRequest):
        symbols = _validate_deployment_request(body)

        deployment = Deployment(
            id=uuid.uuid4().hex[:12],
            strategy_name=body.strategy_name,
            symbols=tuple(symbols),
            capital=body.capital,
            config=StrategyConfig(
                quantity=body.quantity,
                stoploss_pct=body.stoploss_pct,
                target_pct=body.target_pct,
                trailing_pct=body.trailing_pct,
                max_cycles_per_day=body.max_cycles_per_day,
                start_time=body.start_time,
                end_time=body.end_time,
                timeframe=body.timeframe,
            ),
            enabled=body.enabled,
        )
        container.deployment_repository.save_deployment(deployment)
        return _deployment_to_dict(deployment)

    @app.put("/api/deployments/{deployment_id}")
    def update_deployment(deployment_id: str, body: DeploymentRequest):
        if container.deployment_repository.get_deployment(deployment_id) is None:
            raise NotFoundError(f"Unknown deployment: {deployment_id}")

        symbols = _validate_deployment_request(body)

        deployment = Deployment(
            id=deployment_id,
            strategy_name=body.strategy_name,
            symbols=tuple(symbols),
            capital=body.capital,
            config=StrategyConfig(
                quantity=body.quantity,
                stoploss_pct=body.stoploss_pct,
                target_pct=body.target_pct,
                trailing_pct=body.trailing_pct,
                max_cycles_per_day=body.max_cycles_per_day,
                start_time=body.start_time,
                end_time=body.end_time,
                timeframe=body.timeframe,
            ),
            enabled=body.enabled,
        )
        container.deployment_repository.save_deployment(deployment)
        return _deployment_to_dict(deployment)

    @app.delete("/api/deployments/{deployment_id}")
    def delete_deployment(deployment_id: str):
        container.deployment_repository.delete_deployment(deployment_id)
        return {"deleted": deployment_id}

    # -----------------------------
    # REST: watchlist
    # -----------------------------
    @app.get("/api/watchlist")
    def watchlist():
        return {"symbols": container.watchlist_repository.get_symbols()}

    @app.put("/api/watchlist")
    def update_watchlist(body: WatchlistUpdateRequest):
        cleaned = list(dict.fromkeys(s.strip().upper() for s in body.symbols if s.strip()))
        if not cleaned:
            raise ValidationError("Watchlist cannot be empty.")

        container.watchlist_repository.save_symbols(cleaned)
        return {"symbols": cleaned}

    # -----------------------------
    # REST: market-wide ORB screener (display only, independent of deployments)
    # -----------------------------
    @app.get("/api/stage-results")
    def api_stage_results(strategy: str = "ORB"):
        return stage_results.get(strategy.upper(), {})

    @app.get("/api/screener-live")
    def screener_live():
        snapshot = container.trading_engine.get_snapshot()
        orb_stages = stage_results.get("ORB", {})

        s1 = orb_stages.get("stage1", {}).get("stocks", [])
        s2 = orb_stages.get("stage2", {}).get("stocks", [])
        s3 = orb_stages.get("stage3", {}).get("stocks", [])

        result = []
        for symbol, data in snapshot.items():
            stage = "None"
            if symbol in s3:
                stage = "Stage 3"
            elif symbol in s2:
                stage = "Stage 2"
            elif symbol in s1:
                stage = "Stage 1"

            result.append({
                "symbol": symbol,
                "stage": stage,
                "ltp": data.ltp,
                "vwap": data.vwap,
                "rsi": data.rsi,
                "volume_ratio": data.volume_ratio,
                "atr_pct": data.atr_pct,
                "orb_low": data.orb_low,
                "distance_to_or_low": data.distance_to_or_low,
            })

        return result

    # -----------------------------
    # REST: market analysis
    # -----------------------------
    @app.get("/api/market-analysis")
    def api_market_analysis(symbol: str = "NIFTY 50"):
        return analysis_engine.analyze(symbol)

    @app.get("/api/download-report")
    def download_report(symbol: str = "NIFTY 50"):
        data = analysis_engine.analyze(symbol)
        filepath = generate_report(data, symbol)
        return {"file": filepath}

    # -----------------------------
    # REST: end-of-day trades/metrics report
    # -----------------------------
    # Normally written automatically at settings.eod_report_time (see
    # live/eod_scheduler.py) — this endpoint exists so it can be generated
    # on demand too (e.g. to verify paper trading before end of day), and
    # so any past day can be regenerated for analysis via ?date=YYYY-MM-DD.
    @app.get("/api/eod-report")
    def eod_report(date: Optional[str] = None):
        report_date = dt.date.fromisoformat(date) if date else None
        filepath = generate_eod_report(
            container.session_factory,
            container.deployment_repository,
            report_date,
            settings.eod_report_dir,
        )
        return {"file": filepath}

    return app
