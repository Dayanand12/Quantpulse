import datetime as dt

from runners.paper_trading.feed_watchdog import check_feed_health

MARKET_HOURS = dt.datetime(2026, 8, 11, 11, 0)  # 11:00, well within 09:15-15:30
BEFORE_OPEN = dt.datetime(2026, 8, 11, 8, 0)
AFTER_CLOSE = dt.datetime(2026, 8, 11, 18, 0)
THRESHOLD = 60


def test_no_alert_while_no_tick_has_ever_arrived():
    was_stale, message = check_feed_health(None, False, THRESHOLD, MARKET_HOURS)
    assert was_stale is False
    assert message is None


def test_no_alert_when_fresh():
    was_stale, message = check_feed_health(5.0, False, THRESHOLD, MARKET_HOURS)
    assert was_stale is False
    assert message is None


def test_alerts_once_on_going_stale():
    was_stale, message = check_feed_health(120.0, False, THRESHOLD, MARKET_HOURS)
    assert was_stale is True
    assert message is not None
    assert "quiet" in message


def test_stays_silent_while_still_stale():
    was_stale, message = check_feed_health(150.0, True, THRESHOLD, MARKET_HOURS)
    assert was_stale is True
    assert message is None


def test_alerts_once_on_recovery():
    was_stale, message = check_feed_health(2.0, True, THRESHOLD, MARKET_HOURS)
    assert was_stale is False
    assert message is not None
    assert "again" in message


def test_silent_outside_market_hours_even_if_stale():
    was_stale, message = check_feed_health(9999.0, False, THRESHOLD, BEFORE_OPEN)
    assert was_stale is False
    assert message is None

    was_stale, message = check_feed_health(9999.0, False, THRESHOLD, AFTER_CLOSE)
    assert was_stale is False
    assert message is None


def test_outside_market_hours_preserves_existing_stale_state_without_reminding():
    was_stale, message = check_feed_health(9999.0, True, THRESHOLD, AFTER_CLOSE)
    assert was_stale is True
    assert message is None
