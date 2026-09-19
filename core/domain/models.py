"""Domain models: plain, framework-agnostic value objects.

No SQLAlchemy, no Pydantic, no FastAPI types here — this is the vocabulary
every module (paper trading, live trading, backtesting, risk, portfolio,
analytics) speaks, independent of how any one of them is implemented or
transported over HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from core.domain.enums import OrderSide, OrderStatus, TradingMode


@dataclass(frozen=True)
class Instrument:
    symbol: str
    exchange: str


@dataclass(frozen=True)
class InstrumentRef:
    """Broker-assigned identity for a symbol — the instrument_token and
    actual listing exchange from Kite's own instrument dump. Not used by
    any trading/backtesting logic; exists only for building external
    deep-links (e.g. a Kite chart URL), which need the same instrument
    identity Kite Web itself uses."""

    instrument_token: int
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
    # When the position was actually opened — None for trades closed
    # before this field existed, or whose position was already open in
    # memory when it was added (see PaperBroker.enter()/exit()). Needed to
    # locate a trade on an external chart, where closed_at alone only
    # marks the exit.
    opened_at: Optional[datetime] = None
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
    # Open interest at entry, for a STOCK option contract only — the raw
    # value straight from Data_ingestion/options_ingest_stock.py's `oi`
    # column (see snapshot_builder.py). None for equity, for index options
    # (that source has no OI at all — see options_ingest_index.py's
    # docstring), and for trades logged before this field existed.
    entry_oi: Optional[float] = None
    # Human-readable summary of the above (see core/domain/market_condition.py),
    # e.g. "Trending / High Volume / Above VWAP" — denormalized here so
    # reports don't need to recompute it from the raw values.
    market_condition: Optional[str] = None

    # Structured regime dimensions (see core/domain/regime_snapshot.py),
    # captured at the SAME entry moment as market_condition above but kept
    # as independent columns instead of one composite string — so "which
    # strategy works in which regime" can be sliced dimension by dimension
    # (Strategy x regime_trend, Strategy x vix_bucket, ...) without
    # fragmenting sample size across every possible combination. None
    # wherever that dimension's inputs weren't available (a symbol this
    # account doesn't track, e.g. INDIA VIX dropped from the watchlist) or
    # for trades logged before these fields existed.
    #
    # regime_trend/regime_volatility: the traded symbol's OWN regime
    # (classify_regime()'s "regime"/"volatility_state" — Bullish/Bearish
    # Trend, Range, Transition / Compressed, Normal, High Expansion).
    regime_trend: Optional[str] = None
    regime_volatility: Optional[str] = None
    # index_trend: NIFTY 50's own regime at the same moment — a stock can
    # trend while the index chops (or vice versa), and that divergence is
    # often the actual edge, not just the stock's own reading.
    index_trend: Optional[str] = None
    # vix_bucket: India VIX level bucket (Low/Medium/High) — the standard
    # "which playbook applies today" dial (see regime_snapshot.py).
    vix_bucket: Optional[str] = None
    # session_phase: Opening (9:15-9:45) / Mid-day / Closing (14:00-15:30)
    # — intraday edges are frequently time-of-day dependent.
    session_phase: Optional[str] = None

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
class OptionContract:
    """Identifies one option contract: underlying + strike + expiry + side.

    `.symbol` is the canonical string identity — passed as the backtest
    engine's `symbol` argument and stored verbatim in
    BacktestRunParams.symbols (see core/domain/backtest_result.py), so an
    option backtest dedupes on the exact same (strategy, symbols,
    risk-settings) identity an equity backtest already does. Deliberately
    NOT a schema change: BacktestRunParams.symbols is already "whatever
    string identifies what was tested" — colon-delimited so it never
    collides with tickers that contain '_' or '-' (BAJAJ-AUTO, M&M) or
    with the comma multi-symbol separator result_persistence.py already
    uses. `.parse()` round-trips it, for whenever a UI needs to render
    strike/expiry/side back out of a stored result.
    """

    underlying: str
    strike: float
    expiry: date
    side: str  # "CE" or "PE"

    def __post_init__(self) -> None:
        if self.side not in ("CE", "PE"):
            raise ValueError(f"side must be 'CE' or 'PE', got {self.side!r}")

    @property
    def symbol(self) -> str:
        return f"{self.underlying.upper()}:{self.strike:g}{self.side}:{self.expiry.isoformat()}"

    @classmethod
    def parse(cls, symbol: str) -> "OptionContract":
        underlying, strike_side, expiry_str = symbol.split(":")
        side = strike_side[-2:]
        strike = float(strike_side[:-2])
        return cls(underlying=underlying, strike=strike, expiry=date.fromisoformat(expiry_str), side=side)


@dataclass(frozen=True)
class Watchlist:
    """A named, user-organized group of symbols (e.g. "Nifty50", "Bank
    stocks"). Every watchlist's symbols are streamed/warmed together — see
    core/container.py::build_container — so this is purely an organizing
    concept for how a human browses/picks symbols, not a routing concept
    for which symbols the live engine tracks.
    """

    id: int
    name: str
    symbols: tuple[str, ...]


@dataclass(frozen=True)
class Deployment:
    """One running instance of a strategy: which symbols it trades, how
    much capital it's allocated, and its risk/sizing config. Multiple
    deployments can reference the same strategy_name with different
    symbols/capital/config — each gets its own capital pool (see
    core/container.py::DeploymentRuntime).

    symbols vs watchlist_id: exactly one is the deployment's real symbol
    source. A fixed `symbols` tuple is a snapshot frozen at create/edit
    time — the classic mode, unchanged. `watchlist_id` instead means "use
    whatever this named Watchlist currently contains" — resolved fresh by
    ExecutionManager on every evaluate() cycle (runners/paper_trading/
    execution_manager.py), so editing the watchlist's symbols propagates
    to every deployment bound to it immediately, live, no restart —
    unlike a strategy's own conditions.json (see json_condition_strategy.py),
    which IS frozen at registry-discovery time with no live-reload path.
    `symbols` is still populated for a watchlist-bound deployment (kept in
    sync as a last-resolved cache — see server/main.py::_deployment_to_dict)
    so every existing symbols-reading caller keeps working unchanged.
    """

    id: str
    strategy_name: str
    symbols: tuple[str, ...]
    capital: float
    config: StrategyConfig
    enabled: bool = True
    watchlist_id: Optional[int] = None
