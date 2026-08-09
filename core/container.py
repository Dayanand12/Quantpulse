"""Composition root.

The ONE place in the codebase allowed to import concrete infrastructure
and existing engine classes directly and wire them behind the
application-layer interfaces. Every other module (API routes, the
deployment runner, future modules) depends on core.application.interfaces
— never on the concrete classes constructed here. To swap an
implementation (e.g. a SQL-backed order repository instead of the
in-memory PaperBroker adapter, or a live-broker market data provider
instead of paper), change exactly one line in build_container — nothing
else in the codebase needs to know.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List

from sqlalchemy.orm import sessionmaker

from core.application.interfaces.charge_config_repository import IChargeConfigRepository
from core.application.interfaces.current_user_provider import ICurrentUserProvider
from core.application.interfaces.deployment_repository import IDeploymentRepository
from core.application.interfaces.event_bus import IEventBus
from core.application.interfaces.market_data_provider import IMarketDataProvider
from core.application.interfaces.notification_service import INotificationService
from core.application.interfaces.order_repository import IOrderRepository
from core.application.interfaces.portfolio_service import IPortfolioService
from core.application.interfaces.regime_call_repository import IRegimeCallRepository
from core.application.interfaces.risk_engine import IRiskEngine
from core.application.interfaces.strategy_registry import IStrategyRegistry
from core.application.interfaces.strategy_source_repository import IStrategySourceRepository
from core.application.interfaces.trade_repository import ITradeRepository
from core.application.interfaces.trading_engine import ITradingEngine
from core.application.interfaces.watchlist_repository import IWatchlistRepository
from core.domain.indicator_registry import IndicatorSpec
from core.domain.models import Deployment, StrategyConfig
from core.domain.strategy_conditions import required_indicators_from_json

from infrastructure.auth.single_user_provider import SingleUserProvider
from infrastructure.config.settings import Settings
from infrastructure.events.in_process_event_bus import InProcessEventBus
from infrastructure.notifications.console_notification_service import ConsoleNotificationService
from infrastructure.persistence.database import create_session_factory
from infrastructure.persistence.sql_charge_config_repository import SqlChargeConfigRepository
from infrastructure.persistence.sql_deployment_repository import SqlDeploymentRepository
from infrastructure.persistence.sql_regime_call_repository import SqlRegimeCallRepository
from infrastructure.persistence.sql_trade_journal import SqlTradeJournal
from infrastructure.persistence.sql_trade_repository import SqlTradeRepository
from infrastructure.persistence.sql_watchlist_repository import SqlWatchlistRepository
from infrastructure.risk.permissive_risk_engine import PermissiveRiskEngine
from infrastructure.strategies.file_strategy_registry import FileStrategyRegistry
from infrastructure.strategies.filesystem_strategy_source_repository import (
    FilesystemStrategySourceRepository,
)
from infrastructure.trading.live_engine_adapter import LiveEngineAdapter
from infrastructure.trading.market_data.zerodha_provider import ZerodhaMarketDataProvider
from infrastructure.trading.paper_order_repository import PaperOrderRepository
from infrastructure.trading.paper_portfolio_service import PaperPortfolioService

from runners.paper_trading.execution_manager import ExecutionManager
from runners.paper_trading.live_engine import LiveEngine
from runners.paper_trading.paper_broker import PaperBroker
from runners.paper_trading.warm_start import warm_start_indicators
from Data_ingestion.client import ZerodhaClient
from Data_ingestion.config_loader import load_stocks
import strategies as strategies_package

DEFAULT_STRATEGY_NAME = "orb_reversal"


def _required_dynamic_indicators_for_deployments(
    deployments: List[Deployment], strategies_dir: Path = None
) -> List[IndicatorSpec]:
    """Union of every ENABLED deployment's dynamically-requested
    indicators (core/domain/indicator_registry.py — a strategy's
    conditions.json asking for something beyond the always-computed
    fixed set), deduplicated by canonical key. Resolved once here, same
    as every other per-deployment thing this function builds — a
    disabled deployment's strategy never gets evaluated, so its
    indicators aren't worth computing for every symbol on every tick.
    strategies_dir defaults to the real strategies/ package; overridable
    so tests can point it at an isolated tmp directory."""
    strategies_dir = strategies_dir or Path(strategies_package.__path__[0])
    seen: dict = {}
    for deployment in deployments:
        if not deployment.enabled:
            continue
        path = strategies_dir / f"{deployment.strategy_name}.json"
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        for spec in required_indicators_from_json(raw):
            seen.setdefault(spec.key, spec)
    return list(seen.values())


@dataclass
class DeploymentRuntime:
    """One running strategy instance: its own capital pool (own
    PaperBroker behind order_repository/portfolio_service), its own
    ExecutionManager evaluating its own symbol subset with its own
    strategy and risk/sizing config."""

    deployment: Deployment
    order_repository: IOrderRepository
    portfolio_service: IPortfolioService
    execution_manager: ExecutionManager


@dataclass
class Container:
    """Everything the API layer and background workers depend on. Always
    access fields through their interface type — the concrete class behind
    a field can change without any caller changing.
    """

    event_bus: IEventBus
    trading_engine: ITradingEngine
    market_data_provider: IMarketDataProvider
    risk_engine: IRiskEngine
    notification_service: INotificationService
    current_user_provider: ICurrentUserProvider
    watchlist_repository: IWatchlistRepository
    strategy_registry: IStrategyRegistry
    strategy_source_repository: IStrategySourceRepository
    deployment_repository: IDeploymentRepository
    deployment_runtimes: List[DeploymentRuntime]

    # Filtered/aggregated read access over the `trades` table (survives
    # restarts, spans past/deleted deployments) — what the analytics API
    # queries. backend/eod_report.py still uses session_factory directly
    # for its own day-scoped query; both share the same TradeRecord
    # mapping via infrastructure/persistence/sql_trade_repository.py.
    trade_repository: ITradeRepository

    # Exposed so anything needing durable trade history (e.g.
    # backend/eod_report.py) can query the `trades` table directly,
    # without every caller threading its own session factory through.
    session_factory: sessionmaker

    # backend/filter_engine.py's display-only screener loop (the Screener
    # page / Live Dashboard funnel) works directly on LiveEngine's raw dict
    # snapshot — existing, tested, untouched — so it needs the concrete
    # engine, not the ITradingEngine interface the API layer uses. Exposed
    # here as a documented exception rather than routed through a guessed
    # interface for a single, display-only caller.
    live_engine: LiveEngine

    # backend/market_analysis_engine.py needs to pull historical candles
    # for an arbitrary symbol on demand (not just whatever's in the
    # watchlist's live tick cache) — that's a REST call IMarketDataProvider
    # doesn't expose (it's ticks-only, see its docstring), so the concrete
    # client is exposed directly, same documented-exception spirit as
    # live_engine above.
    zerodha_client: ZerodhaClient

    # backend/market_analysis_engine.py logs every _classify() call here
    # and reads back a rolling win rate for the Decision panel's accuracy
    # stat block (see core/application/interfaces/regime_call_repository.py);
    # runners/paper_trading/regime_call_evaluator.py backfills the forward
    # returns that win rate is computed from.
    regime_call_repository: IRegimeCallRepository

    # The editable brokerage/tax rate card (core/domain/charges.py) — used
    # both by each deployment's PaperOrderRepository at trade-close time and
    # by server/main.py's GET/PUT /api/settings/charges.
    charge_config_repository: IChargeConfigRepository


def build_container(settings: Settings, zerodha_client: ZerodhaClient) -> Container:
    """The one function allowed to construct concrete infrastructure."""

    session_factory = create_session_factory(settings.database_url)
    watchlist_repository: IWatchlistRepository = SqlWatchlistRepository(session_factory)
    strategy_registry: IStrategyRegistry = FileStrategyRegistry()
    strategy_source_repository: IStrategySourceRepository = FilesystemStrategySourceRepository(
        Path(strategies_package.__path__[0])
    )
    deployment_repository: IDeploymentRepository = SqlDeploymentRepository(session_factory)
    trade_repository: ITradeRepository = SqlTradeRepository(session_factory)
    regime_call_repository: IRegimeCallRepository = SqlRegimeCallRepository(session_factory)
    charge_config_repository: IChargeConfigRepository = SqlChargeConfigRepository(session_factory)

    symbols = watchlist_repository.get_symbols()
    if not symbols:
        # First run: nothing saved yet — seed from the legacy stocks.json so
        # the transition to a persisted watchlist doesn't lose anything.
        symbols = load_stocks(settings.zerodha_stocks_file)
        watchlist_repository.save_symbols(symbols)

    deployments = deployment_repository.list_deployments()
    if not deployments:
        # First run: seed Deployment 1 from what's been running all along
        # (the whole watchlist, full capital, tested default risk config)
        # so this change doesn't reset or stop anything currently working.
        seed = Deployment(
            id=uuid.uuid4().hex[:12],
            strategy_name=DEFAULT_STRATEGY_NAME,
            symbols=tuple(symbols),
            capital=settings.initial_capital,
            config=StrategyConfig(),
        )
        deployment_repository.save_deployment(seed)
        deployments = [seed]

    event_bus = InProcessEventBus()
    SqlTradeJournal(session_factory, event_bus)

    extra_indicators = _required_dynamic_indicators_for_deployments(deployments)
    live_engine = LiveEngine(symbols, capital=settings.initial_capital, extra_indicators=extra_indicators)
    warm_start_indicators(live_engine, zerodha_client, symbols, zerodha_client.exchange)
    trading_engine: ITradingEngine = LiveEngineAdapter(live_engine)

    market_data_provider: IMarketDataProvider = ZerodhaMarketDataProvider(
        zerodha_client, zerodha_client.exchange
    )

    notification_service: INotificationService = ConsoleNotificationService(event_bus)
    risk_engine: IRiskEngine = PermissiveRiskEngine()
    current_user_provider: ICurrentUserProvider = SingleUserProvider()

    deployment_runtimes: List[DeploymentRuntime] = []
    for deployment in deployments:
        if not deployment.enabled:
            continue

        broker = PaperBroker(deployment.capital)
        order_repository = PaperOrderRepository(
            broker,
            event_bus,
            deployment.id,
            deployment.strategy_name,
            charge_config_repository=charge_config_repository,
        )
        portfolio_service = PaperPortfolioService(broker)
        strategy = strategy_registry.get_strategy(deployment.strategy_name)

        execution_manager = ExecutionManager(
            live_engine,
            order_repository,
            strategy,
            list(deployment.symbols),
            quantity=deployment.config.quantity,
            stoploss_pct=deployment.config.stoploss_pct,
            target_pct=deployment.config.target_pct,
            trailing_pct=deployment.config.trailing_pct,
            max_cycles_per_day=deployment.config.max_cycles_per_day,
            timeframe=deployment.config.timeframe,
        )

        deployment_runtimes.append(
            DeploymentRuntime(
                deployment=deployment,
                order_repository=order_repository,
                portfolio_service=portfolio_service,
                execution_manager=execution_manager,
            )
        )

    return Container(
        event_bus=event_bus,
        trading_engine=trading_engine,
        market_data_provider=market_data_provider,
        risk_engine=risk_engine,
        notification_service=notification_service,
        current_user_provider=current_user_provider,
        watchlist_repository=watchlist_repository,
        strategy_registry=strategy_registry,
        strategy_source_repository=strategy_source_repository,
        deployment_repository=deployment_repository,
        deployment_runtimes=deployment_runtimes,
        live_engine=live_engine,
        zerodha_client=zerodha_client,
        trade_repository=trade_repository,
        session_factory=session_factory,
        regime_call_repository=regime_call_repository,
        charge_config_repository=charge_config_repository,
    )
