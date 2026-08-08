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
from dataclasses import dataclass
from typing import List, Optional

import polars as pl

from core.application.interfaces.strategy import IStrategy
from core.domain.charges import ChargeConfig, compute_charges
from core.domain.enums import OrderSide
from core.domain.market_condition import classify_market_condition
from core.domain.models import StrategyConfig, Trade
from runners.backtesting.snapshot_builder import build_snapshot_series
from runners.paper_trading.live_engine import SUPPORTED_TIMEFRAMES

# Keys forwarded to IStrategy.screen() — exactly LiveEngine.get_snapshot()'s
# per-symbol shape (see live_engine.py::_update_snapshot). `high`/`low`
# in the precomputed series are for this module's own SL/target checks
# and must never leak into what a strategy sees.
_STRATEGY_SNAPSHOT_KEYS = (
    "ltp", "ema5", "ema9", "ema21", "rsi", "adx", "atr_pct",
    "vwap", "volume_ratio", "orb_low", "distance_to_or_low",
)


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
    exact problem for live trading)."""

    timeframe_minutes = SUPPORTED_TIMEFRAMES[config.timeframe]
    bars = build_snapshot_series(base_df, timeframe_minutes)

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
            snapshot = {k: row[k] for k in _STRATEGY_SNAPSHOT_KEYS}
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
