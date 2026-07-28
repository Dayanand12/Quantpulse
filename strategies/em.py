from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide


class MyStrategy(IStrategy):
    # Unique id — this is what you select when deploying on the
    # Strategies page. Lowercase letters, digits, underscores only.
    name = "my_strategy"
    display_name = "My Strategy"
    side = OrderSide.SELL  # or OrderSide.BUY

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        """Return the subset of `symbols` this strategy wants to enter now.

        snapshot[symbol] is a dict with: ltp, ema9, ema21, rsi, adx,
        atr_pct, vwap, volume_ratio, orb_low, distance_to_or_low.
        Risk/sizing (quantity, SL%, target%, trailing%, max cycles) is set
        per-deployment on the Strategies page, not here.
        """
        candidates = []
        for symbol in symbols:
            data = snapshot.get(symbol)
            if not data:
                continue
            # TODO: your entry condition here
            candidates.append(symbol)
        return candidates
