"""Domain events: the vocabulary modules use to talk to each other.

A module publishes an event when something domain-meaningful happens; any
number of other modules (present or future) can subscribe without the
publisher knowing or caring who's listening. This is what lets a future
module (Alerts, Trade Journal, Analytics, AI Assistant) plug in by adding a
subscriber — never by editing the code that publishes the event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from core.domain.enums import NotificationLevel
from core.domain.models import Order, Position, PortfolioSnapshot, Trade


@dataclass(frozen=True)
class DomainEvent:
    occurred_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class PriceUpdated(DomainEvent):
    symbol: str = ""
    ltp: float = 0.0


@dataclass(frozen=True)
class OrderPlaced(DomainEvent):
    order: Order = None  # type: ignore[assignment]


@dataclass(frozen=True)
class OrderExecuted(DomainEvent):
    order: Order = None  # type: ignore[assignment]


@dataclass(frozen=True)
class PositionOpened(DomainEvent):
    position: Position = None  # type: ignore[assignment]


@dataclass(frozen=True)
class PositionClosed(DomainEvent):
    trade: Trade = None  # type: ignore[assignment]


@dataclass(frozen=True)
class PortfolioUpdated(DomainEvent):
    snapshot: PortfolioSnapshot = None  # type: ignore[assignment]


@dataclass(frozen=True)
class NotificationRaised(DomainEvent):
    level: NotificationLevel = NotificationLevel.INFO
    message: str = ""


@dataclass(frozen=True)
class StrategyStarted(DomainEvent):
    strategy_name: str = ""


@dataclass(frozen=True)
class ScreenerStageChanged(DomainEvent):
    strategy_name: str = ""
    stage: str = ""
    symbols: tuple[str, ...] = ()
