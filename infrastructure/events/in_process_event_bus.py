"""Default IEventBus: a thread-safe, synchronous, in-process pub/sub.

Callers include the tick thread, the screener thread, and (via FastAPI) the
asyncio event loop, so subscribe/publish must be safe to call from any of
them. Handlers run synchronously on the publisher's thread — keep them fast,
or have a handler hand off to a queue/executor itself. That policy choice
belongs to whoever writes the handler, not to the bus.
"""

import threading
from collections import defaultdict
from typing import Callable, DefaultDict, List, Type

from core.application.interfaces.event_bus import IEventBus
from core.domain.events import DomainEvent
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class InProcessEventBus(IEventBus):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handlers: DefaultDict[Type[DomainEvent], List[Callable]] = defaultdict(list)

    def publish(self, event: DomainEvent) -> None:
        with self._lock:
            handlers = list(self._handlers.get(type(event), ()))

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("Event handler failed for %s", type(event).__name__)

    def subscribe(self, event_type: Type[DomainEvent], handler: Callable) -> None:
        with self._lock:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: Type[DomainEvent], handler: Callable) -> None:
        with self._lock:
            handlers = self._handlers.get(event_type)
            if handlers and handler in handlers:
                handlers.remove(handler)
