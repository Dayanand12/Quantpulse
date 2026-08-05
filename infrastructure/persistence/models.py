"""ORM models.

TradeRecord mirrors core.domain.models.Trade. Every closed trade is
persisted here by infrastructure/persistence/sql_trade_journal.py (a
PositionClosed subscriber) so trade history survives a backend restart
and past days stay queryable for the EOD report / future analysis — not
just whatever's still in PaperBroker's in-memory trade_log.

WatchlistSymbolRecord and DeploymentRecord ARE also wired in (see
sql_watchlist_repository.py / sql_deployment_repository.py).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.persistence.database import Base


class TradeRecord(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float)
    closed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    initial_stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    deployment_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    strategy_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entry_rsi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_adx: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_atr_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_vwap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_volume_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_condition: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class WatchlistSymbolRecord(Base):
    __tablename__ = "watchlist_symbols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True)


class DeploymentRecord(Base):
    """One row per running strategy instance. `symbols_json` is a JSON-
    encoded list — SQLite has no native array column and a join table
    would be overkill for what's just a handful of symbols per deployment.
    """

    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(64))
    symbols_json: Mapped[str] = mapped_column(Text)
    capital: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    stoploss_pct: Mapped[float] = mapped_column(Float)
    target_pct: Mapped[float] = mapped_column(Float)
    trailing_pct: Mapped[float] = mapped_column(Float)
    max_cycles_per_day: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    start_time: Mapped[str] = mapped_column(String(5), default="09:20")
    end_time: Mapped[str] = mapped_column(String(5), default="11:30")
    timeframe: Mapped[str] = mapped_column(String(10), default="minute")


class RegimeCallRecord(Base):
    """One row per _classify() output (services/market_analysis_engine.py),
    logged once per (symbol, logged_at) — logged_at is the closed candle's
    timestamp, not the poll time, so repeated 5s polls against the same
    unchanged candle don't pile up duplicate rows.

    return_15m/30m/60m start out NULL and get filled in later by
    runners/paper_trading/regime_call_evaluator.py once that much time has
    actually elapsed — they're % price change from `ltp` at the matching
    horizon, sign-agnostic (win/loss is derived from suggested_side at
    query time, not stored).
    """

    __tablename__ = "regime_calls"
    __table_args__ = (UniqueConstraint("symbol", "logged_at", name="uq_regime_calls_symbol_logged_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ltp: Mapped[float] = mapped_column(Float)
    regime: Mapped[str] = mapped_column(String(32))
    trend_strength: Mapped[str] = mapped_column(String(16))
    volatility_state: Mapped[str] = mapped_column(String(16))
    confidence_score: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(32))
    suggested_side: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    return_15m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    return_30m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    return_60m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
