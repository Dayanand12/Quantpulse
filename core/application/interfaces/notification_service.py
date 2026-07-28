"""Port: publish a notification without knowing who ultimately receives it.

The default adapter just logs. Future adapters (email, SMS, push, in-app
toast) subscribe to the same NotificationRaised event or implement this
same interface — callers never change.
"""

from abc import ABC, abstractmethod

from core.domain.enums import NotificationLevel


class INotificationService(ABC):
    @abstractmethod
    def notify(self, level: NotificationLevel, message: str) -> None:
        """Raise a notification. Delivery mechanism is the adapter's concern."""
