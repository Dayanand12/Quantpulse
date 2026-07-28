"""Structured, extensible logging setup.

One configure_logging() call at process startup replaces the bare print()
statements scattered through live/, backend/, and Data_ingestion/ over time.
Existing print() calls are left alone for now (out of scope for this
backbone pass) — new code should use get_logger(__name__) instead.
"""

import json
import logging
import sys
from datetime import datetime, timezone

from infrastructure.config.settings import Environment, Settings


class JsonFormatter(logging.Formatter):
    """One JSON object per line — easy to ship to any future log aggregator."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


_CONFIGURED = False


def configure_logging(settings: Settings) -> None:
    """Idempotent: safe to call more than once (e.g. in tests)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(settings.log_level)

    handler = logging.StreamHandler(sys.stdout)

    if settings.environment is Environment.PRODUCTION:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )

    root.handlers.clear()
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
