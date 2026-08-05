# live/eod_scheduler.py
"""Background thread that fires once a day at settings.eod_report_time
and writes the end-of-day trades/metrics report — no manual click
needed. A simple poll loop (checked every 30s) rather than a cron
library: this process already runs several similar daemon threads (see
run_live.py) and a fixed one-shot-per-day fire doesn't need more than
that.

Reads from the trades table (persisted as trades close — see
infrastructure/persistence/sql_trade_journal.py), so even if this
process is restarted right after the report fires, the data behind it
isn't lost.
"""

import time
from datetime import datetime

from sqlalchemy.orm import sessionmaker

from services.eod_report import generate_eod_report
from core.application.interfaces.deployment_repository import IDeploymentRepository
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_POLL_SECONDS = 30


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def run_eod_scheduler(
    session_factory: sessionmaker,
    deployment_repository: IDeploymentRepository,
    report_time: str,
    output_dir: str,
) -> None:
    """Blocks forever — run this in a daemon thread."""
    hour, minute = _parse_hhmm(report_time)
    last_run_date = None

    while True:
        now = datetime.now()
        due = now.hour > hour or (now.hour == hour and now.minute >= minute)

        if due and last_run_date != now.date():
            try:
                path = generate_eod_report(session_factory, deployment_repository, output_dir=output_dir)
                logger.info("EOD report written to %s", path)
            except Exception:
                logger.exception("Failed to generate EOD report")
            last_run_date = now.date()

        time.sleep(_POLL_SECONDS)
