"""RSI Oversold Bounce (Long) — Larry Connors-style mean-reversion.

Classic proven intraday approach: don't fight the primary trend, but buy
sharp, short-term pullbacks within it. Requires price above ema21 (the
uptrend filter) AND RSI14 dipping into oversold territory (<=30) and
then turning back up — the pullback-is-over signal — rather than
buying the falling knife the moment RSI crosses below 30. Exit is
handled entirely by the universal SL/target/trailing machinery in
runners/paper_trading/execution_manager.py, same as every other
strategy — nothing here decides when to exit.

Tracks each symbol's previous RSI reading on the instance (the registry
keeps one instance alive for the process's lifetime) so screen() fires
only on the upturn tick itself, not on every tick RSI happens to
already be below the oversold line.
"""

from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide

OVERSOLD_RSI = 30


class RsiMeanReversionStrategy(IStrategy):
    name = "rsi_mean_reversion"
    display_name = "RSI Oversold Bounce (Long)"
    side = OrderSide.BUY

    def __init__(self) -> None:
        self._previous_rsi: Dict[str, float] = {}

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        candidates = []

        for symbol in symbols:
            data = snapshot.get(symbol)
            if not data:
                continue

            ltp = data.get("ltp")
            ema21 = data.get("ema21")
            rsi = data.get("rsi")
            if None in (ltp, ema21, rsi):
                continue

            previous_rsi = self._previous_rsi.get(symbol)
            self._previous_rsi[symbol] = rsi
            if previous_rsi is None:
                continue

            uptrend = ltp > ema21
            turning_up_from_oversold = previous_rsi <= OVERSOLD_RSI < rsi

            if uptrend and turning_up_from_oversold:
                candidates.append(symbol)

        return candidates
