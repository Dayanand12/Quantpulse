"""ORM models.

TradeRecord mirrors core.domain.models.Trade. Every closed trade is
persisted here by infrastructure/persistence/sql_trade_journal.py (a
PositionClosed subscriber) so trade history survives a backend restart
and past days stay queryable for the EOD report / future analysis — not
just whatever's still in PaperBroker's in-memory trade_log.

WatchlistSymbolRecord and DeploymentRecord ARE also wired in (see
sql_watchlist_repository.py / sql_deployment_repository.py).
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
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
    charges: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class ChargeConfigRecord(Base):
    """Single-row table (id is always 1) holding the editable brokerage/tax
    rate card — see core/domain/charges.py::ChargeConfig, whose field names
    this mirrors exactly. A dedicated table rather than reusing
    DeploymentRecord's per-row pattern since there's exactly one rate card
    for the whole account, not one per deployment."""

    __tablename__ = "charge_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brokerage_pct: Mapped[float] = mapped_column(Float)
    brokerage_max_per_order: Mapped[float] = mapped_column(Float)
    stt_pct: Mapped[float] = mapped_column(Float)
    exchange_txn_pct: Mapped[float] = mapped_column(Float)
    sebi_pct: Mapped[float] = mapped_column(Float)
    stamp_duty_pct: Mapped[float] = mapped_column(Float)
    gst_pct: Mapped[float] = mapped_column(Float)


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


class BacktestResultRecord(Base):
    """One row per distinct (strategy, symbols, date range, risk settings)
    combination ever run — see core/domain/backtest_result.py::
    BacktestRunParams for exactly which fields make up that identity, and
    why capital/trades aren't part of it. `result_json` holds everything
    else (metrics, breakdowns, equity curve, symbols actually used) since
    that shape doesn't need its own migration every time a new metric is
    added. Re-running identical params updates this row in place (see
    infrastructure/persistence/sql_backtest_result_repository.py's upsert
    on the unique constraint below) rather than ever creating a duplicate
    — this table is meant to replace manually logging backtest results in
    Excel, so it must never accumulate noise from repeat runs."""

    __tablename__ = "backtest_results"
    __table_args__ = (
        UniqueConstraint(
            "strategy_name", "symbols", "timeframe", "date_from", "date_to",
            "quantity", "stoploss_pct", "target_pct", "trailing_pct",
            "max_cycles_per_day", "start_time", "end_time", "charges_enabled",
            name="uq_backtest_results_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(64), index=True)
    symbols: Mapped[str] = mapped_column(Text)
    timeframe: Mapped[str] = mapped_column(String(10))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    quantity: Mapped[int] = mapped_column(Integer)
    stoploss_pct: Mapped[float] = mapped_column(Float)
    target_pct: Mapped[float] = mapped_column(Float)
    trailing_pct: Mapped[float] = mapped_column(Float)
    max_cycles_per_day: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[str] = mapped_column(String(5))
    end_time: Mapped[str] = mapped_column(String(5))
    charges_enabled: Mapped[bool] = mapped_column(Boolean)
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


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
