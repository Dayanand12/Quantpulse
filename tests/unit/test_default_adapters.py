from core.domain.enums import NotificationLevel, OrderSide
from core.domain.events import NotificationRaised
from infrastructure.auth.single_user_provider import SingleUserProvider
from infrastructure.events.in_process_event_bus import InProcessEventBus
from infrastructure.notifications.console_notification_service import ConsoleNotificationService
from infrastructure.risk.permissive_risk_engine import PermissiveRiskEngine


def test_permissive_risk_engine_approves_every_order():
    engine = PermissiveRiskEngine()

    decision = engine.validate_order("RELIANCE", OrderSide.SELL, 250.0, 50)

    assert decision.approved is True


def test_console_notification_service_publishes_notification_raised():
    bus = InProcessEventBus()
    service = ConsoleNotificationService(bus)
    received = []
    bus.subscribe(NotificationRaised, lambda e: received.append((e.level, e.message)))

    service.notify(NotificationLevel.WARNING, "capital running low")

    assert received == [(NotificationLevel.WARNING, "capital running low")]


def test_single_user_provider_returns_stable_identity():
    provider = SingleUserProvider()

    user1 = provider.get_current_user()
    user2 = provider.get_current_user()

    assert user1 == user2
    assert user1.id == "local"
