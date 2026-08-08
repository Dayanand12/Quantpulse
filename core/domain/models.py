"""Domain models: plain, framework-agnostic value objects.

No SQLAlchemy, no Pydantic, no FastAPI types here — this is the vocabulary
every module (paper trading, live trading, backtesting, risk, portfolio,
analytics) speaks, independent of how any one of them is implemented or
transported over HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.domain.enums import OrderSide, OrderStatus, TradingMode


@dataclass(frozen=True)
class Instrument:
    symbol: str
    exchange: str


@dataclass(frozen=True)
class Tick:
    symbol: str
    ltp: float
    volume: float
    timestamp: datetime
    # Previous session's close, when the feed provides one (Zerodha's OHLC
    # packet does) — lets a raw ticker show day-change without waiting on
    # LiveEngine's candle/indicator pipeline (which indices never populate,
    # since they report zero traded volume).
    prev_close: Optional[float] = None


@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MarketSnapshot:
    """A symbol's latest computed indicators, as of the last closed candle."""

    symbol: str
    ltp: Optional[float]
    ema5: Optional[float] = None
    ema9: Optional[float] = None
    ema21: Optional[float] = None
    rsi: Optional[float] = None
    adx: Optional[float] = None
    atr_pct: Optional[float] = None
    vwap: Optional[float] = None
    volume_ratio: Optional[float] = None
    orb_low: Optional[float] = None
    distance_to_or_low: Optional[float] = None


@dataclass(frozen=True)
class Order:
    id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    status: OrderStatus
    mode: TradingMode
    placed_at: datetime


@dataclass(frozen=True)
class Position:
    symbol: str
    side: OrderSide
    quantity: int
    entry_price: float
    stop_loss: Optional[float] = None
    target: Optional[float] = None


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: OrderSide
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float
    closed_at: datetime = field(default_factory=datetime.now)
    # The stop-loss actually set at entry — the basis for R-multiple
    # (see core/domain/metrics.py). None for trades closed before this
    # field existed; those are simply excluded from R-multiple averaging.
    initial_stop_loss: Optional[float] = None
    # Which deployment/strategy produced this trade — stamped on by
    # PaperOrderRepository (it's constructed per-deployment, so it knows).
    # None for trades logged before these fields existed.
    deployment_id: Optional[str] = None
    strategy_name: Optional[str] = None

    # The market condition the strategy actually saw when it entered —
    # the same indicator snapshot IStrategy.screen() sees (see
    # core/application/interfaces/strategy.py), captured at entry rather
    # than exit since that's what drove the trade decision. Lets a report
    # answer "which strategy works in which condition" instead of just
    # "which strategy is profitable overall". None for trades logged
    # before these fields existed, or if no snapshot was available.
    entry_rsi: Optional[float] = None
    entry_adx: Optional[float] = None
    entry_atr_pct: Optional[float] = None
    entry_vwap: Optional[float] = None
    entry_volume_ratio: Optional[float] = None
    # Human-readable summary of the above (see core/domain/market_condition.py),
    # e.g. "Trending / High Volume / Above VWAP" — denormalized here so
    # reports don't need to recompute it from the raw values.
    market_condition: Optional[str] = None

    # Brokerage + STT + exchange/SEBI charges + stamp duty + GST for this
    # trade's round trip (see core/domain/charges.py). `pnl` above stays the
    # raw price-difference figure; `charges`/`net_pnl` are what the
    # analytics dashboard actually reports as "realized profit". None only
    # for trades closed before this field existed and never backfilled.
    charges: Optional[float] = None
    net_pnl: Optional[float] = None


@dataclass(frozen=True)
class RejectedEntry:
    """A candidate entry ExecutionManager tried and the broker turned
    down — surfaced so "why hasn't this fired" is queryable via the API
    instead of only ever printed to the server console."""

    symbol: str
    side: OrderSide
    quantity: int
    price: float
    required_capital: float
    available_capital: float
    reason: str
    at: datetime


@dataclass(frozen=True)
class PortfolioSnapshot:
    available_capital: float
    open_positions: tuple[Position, ...]
    total_trades: int
    trade_log: tuple[Trade, ...]
    rejected_entries: tuple[RejectedEntry, ...] = ()

    @property
    def realized_pnl(self) -> float:
        return sum(t.pnl for t in self.trade_log)


@dataclass(frozen=True)
class StrategyConfig:
    """Universal risk/sizing parameters — same shape for every strategy,
    regardless of what its signal logic looks like. Defaults mirror the
    tested values in backtest/config.py.

    start_time/end_time gate when live/deployment_runner.py evaluates this
    deployment at all (both entries and exit management) — "HH:MM", 24h,
    same string format as settings.eod_report_time. Defaults match the
    window every deployment used before this was configurable per
    deployment.

    timeframe selects which bar size live/live_engine.py::LiveEngine
    computes this deployment's indicators on — one of
    live.live_engine.SUPPORTED_TIMEFRAMES's keys (Kite's own interval
    naming: "minute", "3minute", "5minute", "10minute", "15minute",
    "30minute"). Every timeframe is derived by resampling the same
    1-minute base data, not fetched separately — see
    docs/plans/per-strategy-timeframes.md. Default "minute" matches every
    deployment's behavior before this was configurable.
    """

    quantity: int = 50
    stoploss_pct: float = 0.8
    target_pct: float = 2.0
    trailing_pct: float = 0.1
    max_cycles_per_day: int = 10
    start_time: str = "09:20"
    end_time: str = "11:30"
    timeframe: str = "minute"


@dataclass(frozen=True)
class Deployment:
    """One running instance of a strategy: which symbols it trades, how
    much capital it's allocated, and its risk/sizing config. Multiple
    deployments can reference the same strategy_name with different
    symbols/capital/config — each gets its own capital pool (see
    core/container.py::DeploymentRuntime).
    """

    id: str
    strategy_name: str
    symbols: tuple[str, ...]
    capital: float
    config: StrategyConfig
    enabled: bool = True
