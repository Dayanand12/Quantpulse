# runners/backtesting/engine.py
"""Bar-by-bar backtest replay. Reuses the exact same IStrategy.screen()
every live/paper deployment calls (core/application/interfaces/strategy.py)
against a precomputed snapshot series (snapshot_builder.py) — so a backtest
result reflects what the strategy would actually have decided, not a
reimplementation that could silently diverge from live behavior.

Entry/exit/sizing math is the SL/target/trailing-stop model every
deployment uses (runners/paper_trading/execution_manager.py), generalized
for BUY/SELL — with one deliberate difference: SL/target here check the
bar's high/low (a level can be touched mid-bar without the close
reflecting it), not just the close, matching the pre-refactor backtest
engine's convention (runners/backtesting/trade_engine.py, since removed)
that Deployment's default stoploss_pct/target_pct/trailing_pct were
originally tuned against. Trailing-stop updates still use the close, same
as live. This trade-off is deliberate: checking only the close would make
the backtest look better than a live/paper run ever could (a stop that
was actually touched mid-bar would be silently skipped).
"""

import datetime as dt
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import polars as pl

from core.application.interfaces.strategy import IStrategy
from core.domain.charges import ChargeConfig, compute_charges
from core.domain.enums import OrderSide
from core.domain.market_condition import classify_market_condition
from core.domain.models import StrategyConfig, Trade
from core.domain.indicator_registry import IndicatorSpec
from core.domain.strategy_conditions import VALID_SNAPSHOT_FIELDS
from infrastructure.config.settings import get_settings
from runners.backtesting.historical_loader import load_equity_csv
from runners.backtesting.snapshot_builder import build_snapshot_series
from runners.paper_trading.live_engine import SUPPORTED_TIMEFRAMES

# The one broader-market symbol a strategy's conditions.json can reference
# via the nifty_* snapshot fields (core/domain/strategy_conditions.py) —
# e.g. "only go long while NIFTY itself is trending up". Hardcoded rather
# than configurable: nothing has asked for a different index yet, and
# adding that is a small extension of _regime_snapshot_series below if it
# ever comes up.
_REGIME_SYMBOL = "NIFTY 50"

# NIFTY 50's own snapshot series, computed once per timeframe and reused
# across every symbol/strategy backtest in this process — its file is
# ~1M rows, far too expensive to reload and re-resample on every single
# run_backtest() call. Keyed by timeframe_minutes; a cached None means
# "checked, the file genuinely isn't there" — `in` (not truthiness) is
# what distinguishes that from "never checked yet", so a missing file
# doesn't get retried on every call either.
_regime_cache: Dict[int, Optional[pl.DataFrame]] = {}


def _regime_snapshot_series(timeframe_minutes: int) -> Optional[pl.DataFrame]:
    if timeframe_minutes in _regime_cache:
        return _regime_cache[timeframe_minutes]

    csv_path = os.path.join(get_settings().historical_data_dir, f"{_REGIME_SYMBOL}_historical.csv")
    try:
        regime_df = load_equity_csv(csv_path)
    except FileNotFoundError:
        _regime_cache[timeframe_minutes] = None
        return None

    bars = build_snapshot_series(regime_df, timeframe_minutes).select(
        "date", "ema9", "ema21", "adx",
    ).rename({"ema9": "nifty_ema9", "ema21": "nifty_ema21", "adx": "nifty_adx"})
    _regime_cache[timeframe_minutes] = bars
    return bars

# Keys forwarded to IStrategy.screen() — exactly LiveEngine.get_snapshot()'s
# per-symbol shape (see live_engine.py::_update_snapshot). `high`/`low`
# in the precomputed series are for this module's own SL/target checks
# and must never leak into what a strategy sees. Same tuple
# ConditionSet.from_dict() validates a strategy's conditions.json field
# references against (core/domain/strategy_conditions.py) — one source of
# truth, so the two can never silently drift apart.
_STRATEGY_SNAPSHOT_KEYS = VALID_SNAPSHOT_FIELDS


@dataclass
class _TradeState:
    side: OrderSide
    entry_price: float
    quantity: int
    stop_loss: float
    target: float
    trail_price: float
    entry_snapshot: dict


def _parse_hhmm(value: str) -> dt.time:
    hour, minute = value.split(":")
    return dt.time(int(hour), int(minute))


def _entry_levels(side: OrderSide, ltp: float, config: StrategyConfig) -> dict:
    if side == OrderSide.SELL:
        return {
            "stop_loss": ltp * (1 + config.stoploss_pct / 100),
            "target": ltp * (1 - config.target_pct / 100),
            "trail_price": ltp,
        }
    return {
        "stop_loss": ltp * (1 - config.stoploss_pct / 100),
        "target": ltp * (1 + config.target_pct / 100),
        "trail_price": ltp,
    }


def _exit_reason(state: _TradeState, high: float, low: float, close: float, config: StrategyConfig) -> Optional[str]:
    if state.side == OrderSide.SELL:
        if high >= state.stop_loss:
            return "SL"
        if low <= state.target:
            return "TP"
        if close < state.trail_price * (1 - config.trailing_pct / 100):
            return "TRAIL"
        state.trail_price = max(state.trail_price, close)
        return None

    # BUY — mirrored
    if low <= state.stop_loss:
        return "SL"
    if high >= state.target:
        return "TP"
    if close > state.trail_price * (1 + config.trailing_pct / 100):
        return "TRAIL"
    state.trail_price = min(state.trail_price, close)
    return None


def run_backtest(
    strategy: IStrategy,
    symbol: str,
    base_df: pl.DataFrame,
    config: StrategyConfig,
    deployment_id: Optional[str] = None,
    charge_config: Optional[ChargeConfig] = None,
    date_from: Optional[dt.date] = None,
    date_to: Optional[dt.date] = None,
    extra_indicators: Optional[List[IndicatorSpec]] = None,
) -> List[Trade]:
    """base_df: 1-minute OHLCV for `symbol` (runners/backtesting/
    historical_loader.load_equity_csv). Returns every closed trade, in the
    same core.domain.models.Trade shape live/paper trading produces.

    date_from/date_to restrict which bars are replayed (e.g. "last 1
    year"), but indicators are still computed over the FULL base_df below
    before that restriction is applied — truncating the input first would
    give EMA/RSI/ADX a cold start right at date_from instead of the warmed-
    up values a live/paper deployment would actually have on that date
    (see runners/paper_trading/warm_start.py, which exists to avoid this
    exact problem for live trading).

    extra_indicators: any indicators `strategy`'s conditions.json needs
    beyond the always-available fixed set (see runners/backtesting/
    result_persistence.py::required_dynamic_indicators, which derives
    this from the strategy's JSON) — forwarded into screen()'s snapshot
    dict alongside the fixed keys, keyed by their canonical name (e.g.
    "ema_20")."""
    extra_indicators = extra_indicators or []
    extra_keys = tuple(spec.key for spec in extra_indicators)

    timeframe_minutes = SUPPORTED_TIMEFRAMES[config.timeframe]
    bars = build_snapshot_series(base_df, timeframe_minutes, extra_indicators=extra_indicators)

    # nifty_ema9/nifty_ema21/nifty_adx (core/domain/strategy_conditions.py's
    # VALID_SNAPSHOT_FIELDS) — joined by exact bar timestamp, so this can
    # never leak a later NIFTY bar into an earlier stock bar: each side's
    # own indicator series is already causally correct (build_snapshot_series
    # never looks ahead), and aligning two already-correct series by their
    # shared timestamp doesn't introduce new lookahead. A bar with no
    # matching NIFTY date (e.g. outside NIFTY's covered range) just gets
    # None for these three columns — ConditionSet.evaluate() already treats
    # any None required field as "condition not met", same as every other
    # snapshot field. Skipped entirely when backtesting NIFTY 50 itself.
    if symbol != _REGIME_SYMBOL:
        regime_bars = _regime_snapshot_series(timeframe_minutes)
        if regime_bars is not None:
            bars = bars.join(regime_bars, on="date", how="left")
    if "nifty_ema9" not in bars.columns:
        bars = bars.with_columns(
            pl.lit(None, dtype=pl.Float64).alias(c) for c in ("nifty_ema9", "nifty_ema21", "nifty_adx")
        )

    if date_from is not None:
        bars = bars.filter(pl.col("date").dt.date() >= date_from)
    if date_to is not None:
        bars = bars.filter(pl.col("date").dt.date() <= date_to)

    start_time = _parse_hhmm(config.start_time)
    end_time = _parse_hhmm(config.end_time)

    trades: List[Trade] = []
    state: Optional[_TradeState] = None
    current_day: Optional[dt.date] = None
    cycles_today = 0

    for row in bars.iter_rows(named=True):
        bar_date: dt.datetime = row["date"]
        bar_time = bar_date.time()
        bar_day = bar_date.date()

        if bar_day != current_day:
            current_day = bar_day
            cycles_today = 0

        if not (start_time <= bar_time <= end_time):
            continue

        # -------- manage the open position's exit first, same order as
        # ExecutionManager.evaluate() (_manage_exits before _manage_entries)
        if state is not None:
            reason = _exit_reason(state, row["high"], row["low"], row["ltp"], config)
            if reason is not None:
                exit_price = state.stop_loss if reason == "SL" else (
                    state.target if reason == "TP" else row["ltp"]
                )
                pnl = (
                    (state.entry_price - exit_price) * state.quantity
                    if state.side == OrderSide.SELL
                    else (exit_price - state.entry_price) * state.quantity
                )

                charges = None
                net_pnl = None
                if charge_config is not None:
                    breakdown = compute_charges(
                        state.entry_price, exit_price, state.quantity, state.side, charge_config
                    )
                    charges = breakdown.total
                    net_pnl = pnl - charges

                snap = state.entry_snapshot
                trades.append(Trade(
                    symbol=symbol,
                    side=state.side,
                    quantity=state.quantity,
                    entry_price=state.entry_price,
                    exit_price=exit_price,
                    pnl=pnl,
                    closed_at=bar_date,
                    initial_stop_loss=state.stop_loss,
                    deployment_id=deployment_id,
                    strategy_name=strategy.name,
                    entry_rsi=snap.get("rsi"),
                    entry_adx=snap.get("adx"),
                    entry_atr_pct=snap.get("atr_pct"),
                    entry_vwap=snap.get("vwap"),
                    entry_volume_ratio=snap.get("volume_ratio"),
                    entry_oi=snap.get("oi"),
                    market_condition=classify_market_condition(
                        ltp=snap.get("ltp"), adx=snap.get("adx"),
                        vwap=snap.get("vwap"), volume_ratio=snap.get("volume_ratio"),
                    ),
                    charges=charges,
                    net_pnl=net_pnl,
                ))
                state = None

        # -------- then entries, mirroring ExecutionManager._manage_entries
        if state is None and cycles_today < config.max_cycles_per_day and row["ltp"] is not None:
            snapshot = {k: row[k] for k in (*_STRATEGY_SNAPSHOT_KEYS, *extra_keys)}
            candidates = strategy.screen({symbol: snapshot}, [symbol])

            if symbol in candidates:
                ltp = row["ltp"]
                levels = _entry_levels(strategy.side, ltp, config)
                state = _TradeState(
                    side=strategy.side,
                    entry_price=ltp,
                    quantity=config.quantity,
                    stop_loss=levels["stop_loss"],
                    target=levels["target"],
                    trail_price=levels["trail_price"],
                    entry_snapshot=snapshot,
                )
                cycles_today += 1

    return trades
