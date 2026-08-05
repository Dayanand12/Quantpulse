"""ITradingEngine implemented by wrapping the existing, tested LiveEngine.

live/live_engine.py is untouched — this adapter only translates between the
domain vocabulary (Tick, MarketSnapshot) and LiveEngine's existing dict-based
API. That keeps the tested indicator/OR/VWAP logic exactly as validated,
while everything above this seam (API routes, future modules) depends only
on ITradingEngine.
"""

from typing import Dict

from core.application.interfaces.trading_engine import ITradingEngine
from core.domain.models import MarketSnapshot, Tick
from runners.paper_trading.live_engine import LiveEngine


class LiveEngineAdapter(ITradingEngine):
    def __init__(self, live_engine: LiveEngine) -> None:
        self._engine = live_engine

    def process_tick(self, symbol: str, tick: Tick) -> None:
        self._engine.process_tick(symbol, {"LTP": tick.ltp, "Volume": tick.volume})

    def get_snapshot(self) -> Dict[str, MarketSnapshot]:
        raw = self._engine.get_snapshot()
        return {
            symbol: MarketSnapshot(
                symbol=symbol,
                ltp=data.get("ltp"),
                ema5=data.get("ema5"),
                ema9=data.get("ema9"),
                ema21=data.get("ema21"),
                rsi=data.get("rsi"),
                adx=data.get("adx"),
                atr_pct=data.get("atr_pct"),
                vwap=data.get("vwap"),
                volume_ratio=data.get("volume_ratio"),
                orb_low=data.get("orb_low"),
                distance_to_or_low=data.get("distance_to_or_low"),
            )
            for symbol, data in raw.items()
        }
