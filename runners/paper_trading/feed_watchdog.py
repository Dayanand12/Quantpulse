# runners/paper_trading/feed_watchdog.py
"""Background thread that watches the live tick feed and pings Telegram if
it goes dead. Closes the exact gap behind the 2026-08-11 incident: the
server stayed fully responsive to HTTP requests for hours while the feed
itself was frozen, so nothing looked wrong unless someone deliberately
checked. Same poll-loop style as eod_scheduler.py.

Debounced on a "was the feed stale last check" flag — one alert fires on
going stale, one on recovering, not once per poll forever.
"""

import time
from datetime import datetime
from typing import Optional, Protocol, Tuple

from core.application.interfaces.market_data_provider import IMarketDataProvider
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_POLL_SECONDS = 30

# NSE cash market hours (IST) — outside this window an idle feed is
# expected, not an incident, so the watchdog stays silent then rather than
# firing a false alarm every evening after close.
_MARKET_OPEN_MINUTES = 9 * 60 + 15
_MARKET_CLOSE_MINUTES = 15 * 60 + 30


class SendsMessages(Protocol):
    def send_message(self, chat_id: int, text: str) -> None: ...


def _within_market_hours(now: datetime) -> bool:
    now_minutes = now.hour * 60 + now.minute
    return _MARKET_OPEN_MINUTES <= now_minutes <= _MARKET_CLOSE_MINUTES


def check_feed_health(
    staleness_seconds: Optional[float],
    was_stale: bool,
    threshold_seconds: int,
    now: datetime,
) -> Tuple[bool, Optional[str]]:
    """Pure decision function (no I/O) — the part worth unit testing in
    isolation from threading/sleep/network. Returns
    (new_was_stale, message_to_send_or_None).

    staleness_seconds is None before the first tick has ever arrived
    (e.g. still warming up at startup) — nothing to alert on yet."""
    if staleness_seconds is None or not _within_market_hours(now):
        return was_stale, None

    is_stale = staleness_seconds > threshold_seconds

    if is_stale and not was_stale:
        return True, (
            f"⚠️ QuantPulse: live feed has gone quiet "
            f"({staleness_seconds:.0f}s since the last tick). Check the process."
        )
    if not is_stale and was_stale:
        return False, "✅ QuantPulse: live feed is receiving ticks again."

    return was_stale, None


def run_feed_watchdog(
    market_data_provider: IMarketDataProvider,
    telegram_client: SendsMessages,
    chat_id: int,
    threshold_seconds: int,
) -> None:
    """Blocks forever — run in a daemon thread. telegram_client duck-types
    TelegramClient.send_message (runners/backtesting/telegram_bot.py)."""
    was_stale = False
    while True:
        try:
            staleness = market_data_provider.seconds_since_last_tick()
            was_stale, message = check_feed_health(staleness, was_stale, threshold_seconds, datetime.now())
            if message:
                logger.warning(message)
                telegram_client.send_message(chat_id, message)
        except Exception:
            logger.exception("feed_watchdog check failed")
        time.sleep(_POLL_SECONDS)
