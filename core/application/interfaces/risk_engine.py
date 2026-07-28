"""Port: pre-trade risk validation.

Interface only, as requested — no real risk rules exist yet. The default
adapter (infrastructure/risk/permissive_risk_engine.py) approves everything
so the system is fully wireable today; a real implementation (position
limits, max daily loss, exposure caps) replaces it later without touching
whatever calls IRiskEngine.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from core.domain.enums import OrderSide


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: Optional[str] = None


class IRiskEngine(ABC):
    @abstractmethod
    def validate_order(
        self, symbol: str, side: OrderSide, price: float, quantity: int
    ) -> RiskDecision:
        """Decide whether an order is allowed to proceed."""
