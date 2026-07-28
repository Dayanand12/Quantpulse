"""Port: the event bus every module publishes to and subscribes through.

This is the seam that keeps modules decoupled. A publisher never imports a
subscriber; both only depend on this interface and the event types in
core.domain.events.
"""

from abc import ABC, abstractmethod
from typing import Callable, Type, TypeVar

from core.domain.events import DomainEvent

TEvent = TypeVar("TEvent", bound=DomainEvent)
EventHandler = Callable[[TEvent], None]


class IEventBus(ABC):
    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        """Publish an event to every handler subscribed to its type."""

    @abstractmethod
    def subscribe(self, event_type: Type[TEvent], handler: EventHandler) -> None:
        """Register a handler to be called whenever event_type is published."""

    @abstractmethod
    def unsubscribe(self, event_type: Type[TEvent], handler: EventHandler) -> None:
        """Remove a previously registered handler."""
