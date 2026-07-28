"""Default INotificationService: logs, and publishes NotificationRaised.

Publishing the event (not just logging) is what makes this extensible —
a future email/SMS/push channel subscribes to NotificationRaised on the
event bus instead of this class growing an if/elif per channel.
"""

import logging

from core.application.interfaces.event_bus import IEventBus
from core.application.interfaces.notification_service import INotificationService
from core.domain.enums import NotificationLevel
from core.domain.events import NotificationRaised
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_LEVEL_MAP = {
    NotificationLevel.INFO: logging.INFO,
    NotificationLevel.WARNING: logging.WARNING,
    NotificationLevel.ERROR: logging.ERROR,
    NotificationLevel.CRITICAL: logging.CRITICAL,
}


class ConsoleNotificationService(INotificationService):
    def __init__(self, event_bus: IEventBus) -> None:
        self._event_bus = event_bus

    def notify(self, level: NotificationLevel, message: str) -> None:
        logger.log(_LEVEL_MAP[level], message)
        self._event_bus.publish(NotificationRaised(level=level, message=message))
