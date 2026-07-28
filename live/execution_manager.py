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
from typing import List

from core.application.interfaces.order_repository import IOrderRepository
from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide


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
    ):
        self.live_engine = live_engine
        self.order_repository = order_repository
        self.strategy = strategy
        self.symbols = symbols
        self.side = strategy.side

        self.quantity = quantity
        self.stoploss_pct = stoploss_pct
        self.target_pct = target_pct
        self.trailing_pct = trailing_pct
        self.max_cycles_per_day = max_cycles_per_day

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

    def _manage_entries(self, snapshot):
        candidates = self.strategy.screen(snapshot, self.symbols)

        for symbol in candidates:
            if self.order_repository.get_open_position(symbol) is not None:
                continue

            if self.trades_today.get(symbol, 0) >= self.max_cycles_per_day:
                continue

            data = snapshot.get(symbol)
            if not data or data.get("ltp") is None:
                continue

            ltp = data["ltp"]

            entered = self.order_repository.open_position(symbol, self.side, ltp, self.quantity)

            if entered:
                self.trade_state[symbol] = self._entry_levels(ltp)
                self.trades_today[symbol] = self.trades_today.get(symbol, 0) + 1

    def evaluate(self):
        self._reset_if_new_day(dt.date.today())

        snapshot = self.live_engine.get_snapshot()

        self._manage_exits(snapshot)
        self._manage_entries(snapshot)
