"""Default IRiskEngine: approves every order.

Explicit placeholder, not a real risk implementation — position limits, max
daily loss, and exposure caps are future work. This exists so the rest of
the system can depend on IRiskEngine today instead of skipping risk checks
entirely, which would make adding real rules later a bigger diff than it
needs to be.
"""

from core.application.interfaces.risk_engine import IRiskEngine, RiskDecision
from core.domain.enums import OrderSide


class PermissiveRiskEngine(IRiskEngine):
    def validate_order(
        self, symbol: str, side: OrderSide, price: float, quantity: int
    ) -> RiskDecision:
        return RiskDecision(approved=True)
