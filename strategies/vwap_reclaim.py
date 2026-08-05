"""VWAP Reclaim (Long) — classic intraday momentum strategy.

Session VWAP is the level intraday desks use to judge whether the
day's flow is net buying or net selling. This strategy waits for price
to cross from below VWAP to above it (a "reclaim") while volume is
running hot (volume_ratio > 1.5x the recent average) and the short-term
trend already agrees (ema9 > ema21) — the combination that separates a
genuine breakout from noise sitting right at VWAP. Exit is handled
entirely by the universal SL/target/trailing machinery in
runners/paper_trading/execution_manager.py, same as every other
strategy — nothing here decides when to exit.

Tracks each symbol's previous close-vs-VWAP relationship on the
instance (the registry keeps one instance alive for the process's
lifetime) so screen() fires only on the crossing tick itself.
"""

from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide

VOLUME_RATIO_THRESHOLD = 1.5


class VwapReclaimStrategy(IStrategy):
    name = "vwap_reclaim"
    display_name = "VWAP Reclaim (Long)"
    side = OrderSide.BUY

    def __init__(self) -> None:
        self._was_below: Dict[str, bool] = {}

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        candidates = []

        for symbol in symbols:
            data = snapshot.get(symbol)
            if not data:
                continue

            ltp = data.get("ltp")
            vwap = data.get("vwap")
            ema9 = data.get("ema9")
            ema21 = data.get("ema21")
            volume_ratio = data.get("volume_ratio")
            if None in (ltp, vwap, ema9, ema21, volume_ratio):
                continue

            was_below = self._was_below.get(symbol)
            self._was_below[symbol] = ltp < vwap
            if was_below is None:
                continue

            reclaimed = was_below and ltp >= vwap
            trending_up = ema9 > ema21
            volume_confirmed = volume_ratio >= VOLUME_RATIO_THRESHOLD

            if reclaimed and trending_up and volume_confirmed:
                candidates.append(symbol)

        return candidates
