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


@dataclass(frozen=True)
class PortfolioSnapshot:
    available_capital: float
    open_positions: tuple[Position, ...]
    total_trades: int
    trade_log: tuple[Trade, ...]

    @property
    def realized_pnl(self) -> float:
        return sum(t.pnl for t in self.trade_log)


@dataclass(frozen=True)
class StrategyConfig:
    """Universal risk/sizing parameters — same shape for every strategy,
    regardless of what its signal logic looks like. Defaults mirror the
    tested values in backtest/config.py.
    """

    quantity: int = 50
    stoploss_pct: float = 0.8
    target_pct: float = 2.0
    trailing_pct: float = 0.1
    max_cycles_per_day: int = 10


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
