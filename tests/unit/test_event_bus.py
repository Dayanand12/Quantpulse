from dataclasses import dataclass

from core.domain.events import DomainEvent
from infrastructure.events.in_process_event_bus import InProcessEventBus


@dataclass(frozen=True)
class _SampleEvent(DomainEvent):
    value: int = 0


def test_publish_calls_subscribed_handler():
    bus = InProcessEventBus()
    received = []

    bus.subscribe(_SampleEvent, lambda e: received.append(e.value))
    bus.publish(_SampleEvent(value=42))

    assert received == [42]


def test_publish_calls_multiple_handlers():
    bus = InProcessEventBus()
    calls = []

    bus.subscribe(_SampleEvent, lambda e: calls.append("first"))
    bus.subscribe(_SampleEvent, lambda e: calls.append("second"))
    bus.publish(_SampleEvent(value=1))

    assert calls == ["first", "second"]


def test_unsubscribe_stops_delivery():
    bus = InProcessEventBus()
    received = []

    def handler(event):
        received.append(event.value)

    bus.subscribe(_SampleEvent, handler)
    bus.unsubscribe(_SampleEvent, handler)
    bus.publish(_SampleEvent(value=99))

    assert received == []


def test_handler_exception_does_not_break_other_handlers():
    bus = InProcessEventBus()
    received = []

    def bad_handler(event):
        raise RuntimeError("boom")

    bus.subscribe(_SampleEvent, bad_handler)
    bus.subscribe(_SampleEvent, lambda e: received.append(e.value))

    bus.publish(_SampleEvent(value=7))  # must not raise

    assert received == [7]


def test_no_subscribers_is_a_noop():
    bus = InProcessEventBus()
    bus.publish(_SampleEvent(value=1))  # must not raise
