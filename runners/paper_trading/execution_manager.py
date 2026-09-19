# live/execution_manager.py
"""
Turns a strategy's screened candidates into simulated paper trades for one
deployment.

SELL-side math mirrors the tested ORB rules from backtest/config.py +
backtest/trade_engine.py (stoploss_pct, target_pct, trailing_pct,
quantity, max_cycles_per_day) exactly, unchanged. BUY-side math is the
mirrored generalization, added so non-ORB (long-biased) strategies can use
the same universal risk/sizing shape.

Depends on IOrderRepository (a port) and IStrategy (a port), not concrete
classes — one ExecutionManager per deployment (see
core/container.py::DeploymentRuntime), each with its own order_repository
(so its own capital pool), symbol subset, and strategy instance.
"""

import datetime as dt
from typing import List, Optional

from core.application.interfaces.order_repository import IOrderRepository
from core.application.interfaces.strategy import IStrategy
from core.application.interfaces.watchlist_repository import IWatchlistRepository
from core.domain.enums import OrderSide

# The two index symbols a trade's entry-time regime snapshot is enriched
# with (core/domain/regime_snapshot.py) — same broader-market symbol
# backtest's engine.py joins by timestamp (_REGIME_SYMBOL), plus INDIA VIX
# for the vix_bucket dimension backtest doesn't have live. Both are
# genuinely optional: absent from live_engine's snapshot (e.g. dropped
# from every watchlist) just means those regime columns come back None on
# the resulting Trade, same as any other missing indicator.
_REGIME_INDEX_SYMBOL = "NIFTY 50"
_REGIME_VIX_SYMBOL = "INDIA VIX"


class ExecutionManager:
    def __init__(
        self,
        live_engine,
        order_repository: IOrderRepository,
        strategy: IStrategy,
        symbols: List[str],
        quantity=50,
        stoploss_pct=0.8,
        target_pct=2.0,
        trailing_pct=0.1,
        max_cycles_per_day=10,
        timeframe="minute",
        watchlist_repository: Optional[IWatchlistRepository] = None,
        watchlist_id: Optional[int] = None,
    ):
        self.live_engine = live_engine
        self.order_repository = order_repository
        self.strategy = strategy
        self.symbols = symbols
        self.side = strategy.side
        # When set, watchlist_id takes over as the real symbol source —
        # current_symbols() re-reads that watchlist fresh every cycle
        # instead of using the frozen `symbols` list above. See
        # core/domain/models.py::Deployment's docstring for why.
        self.watchlist_repository = watchlist_repository
        self.watchlist_id = watchlist_id

        self.quantity = quantity
        self.stoploss_pct = stoploss_pct
        self.target_pct = target_pct
        self.trailing_pct = trailing_pct
        self.max_cycles_per_day = max_cycles_per_day
        self.timeframe = timeframe

        # symbol -> {stop_loss, target, trail_price}
        self.trade_state = {}
        # symbol -> cycles used today
        self.trades_today = {}
        self.current_day = None

    def _reset_if_new_day(self, today):
        if self.current_day != today:
            self.current_day = today
            self.trades_today = {}

    def _entry_levels(self, ltp):
        if self.side == OrderSide.SELL:
            return {
                "stop_loss": ltp * (1 + self.stoploss_pct / 100),
                "target": ltp * (1 - self.target_pct / 100),
                "trail_price": ltp,
            }
        return {
            "stop_loss": ltp * (1 - self.stoploss_pct / 100),
            "target": ltp * (1 + self.target_pct / 100),
            "trail_price": ltp,
        }

    def _exit_reason(self, ltp, state):
        if self.side == OrderSide.SELL:
            if ltp >= state["stop_loss"]:
                return "SL"
            if ltp <= state["target"]:
                return "TP"
            if ltp < state["trail_price"] * (1 - self.trailing_pct / 100):
                return "TRAIL"
            state["trail_price"] = max(state["trail_price"], ltp)
            return None

        # BUY — mirrored
        if ltp <= state["stop_loss"]:
            return "SL"
        if ltp >= state["target"]:
            return "TP"
        if ltp > state["trail_price"] * (1 + self.trailing_pct / 100):
            return "TRAIL"
        state["trail_price"] = min(state["trail_price"], ltp)
        return None

    def _manage_exits(self, snapshot):
        open_symbols = [p.symbol for p in self.order_repository.get_open_positions()]

        for symbol in open_symbols:
            state = self.trade_state.get(symbol)
            data = snapshot.get(symbol)

            if not state or not data or data.get("ltp") is None:
                continue

            ltp = data["ltp"]
            exit_reason = self._exit_reason(ltp, state)

            if exit_reason:
                self.order_repository.close_position(
                    symbol, ltp, initial_stop_loss=state["stop_loss"]
                )
                self.trade_state.pop(symbol, None)

    def current_symbols(self) -> List[str]:
        """The symbol list this cycle actually screens — a watchlist_id
        binding always wins over the frozen `symbols` list when set, and
        is re-read fresh every call (no caching), so a watchlist edit
        takes effect on this deployment's very next 3-second cycle
        (see runners/paper_trading/deployment_runner.py), live."""
        if self.watchlist_id is not None and self.watchlist_repository is not None:
            return self.watchlist_repository.get_symbols(self.watchlist_id)
        return self.symbols

    def _regime_context(self, snapshot) -> dict:
        """NIFTY/VIX fields to merge onto an entry's own snapshot before
        it's stored — a NEW dict each call (never mutates `snapshot`
        in-place: its per-symbol entries are the SAME dict objects
        live_engine.py's indicator_snapshot holds, reused every cycle, so
        writing extra keys into one directly would permanently pollute
        what the strategy sees on every later tick, not just this trade's
        own frozen copy)."""
        index_data = snapshot.get(_REGIME_INDEX_SYMBOL) or {}
        vix_data = snapshot.get(_REGIME_VIX_SYMBOL) or {}
        return {
            "nifty_ltp": index_data.get("ltp"),
            "nifty_ema9": index_data.get("ema9"),
            "nifty_ema21": index_data.get("ema21"),
            "nifty_adx": index_data.get("adx"),
            "nifty_vwap": index_data.get("vwap"),
            "nifty_atr_pct": index_data.get("atr_pct"),
            "vix_ltp": vix_data.get("ltp"),
        }

    def _manage_entries(self, snapshot):
        candidates = self.strategy.screen(snapshot, self.current_symbols())

        for symbol in candidates:
            if self.order_repository.get_open_position(symbol) is not None:
                continue

            if self.trades_today.get(symbol, 0) >= self.max_cycles_per_day:
                continue

            data = snapshot.get(symbol)
            if not data or data.get("ltp") is None:
                continue

            ltp = data["ltp"]
            enriched_snapshot = {**data, **self._regime_context(snapshot)}

            entered = self.order_repository.open_position(
                symbol, self.side, ltp, self.quantity, market_snapshot=enriched_snapshot
            )

            if entered:
                self.trade_state[symbol] = self._entry_levels(ltp)
                self.trades_today[symbol] = self.trades_today.get(symbol, 0) + 1

    def evaluate(self):
        self._reset_if_new_day(dt.date.today())

        snapshot = self.live_engine.get_snapshot(self.timeframe)

        self._manage_exits(snapshot)
        self._manage_entries(snapshot)
