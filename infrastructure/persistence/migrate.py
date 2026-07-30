"""Programmatic `alembic upgrade head`.

Called once at process startup (run_live.py) so the SQLite schema is always
current without a manual migration step — reasonable for a single-instance
local app; a multi-instance/cloud deployment would run this as a separate
release step instead of at every process start.
"""

import logging
import os

from alembic import command
from alembic.config import Config

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ALEMBIC_INI = os.path.join(_PROJECT_ROOT, "alembic.ini")


def run_migrations() -> None:
    # infrastructure/persistence/alembic/env.py calls logging.config.
    # fileConfig(alembic.ini) on every run, which resets the ROOT
    # logger's level/handlers globally (alembic.ini sets root to
    # WARNING) — not scoped to alembic's own loggers. Left alone, every
    # logger.info() call anywhere in the app goes silent for the rest of
    # the process after the very first startup. Snapshot and restore
    # around the upgrade call so the app's own configure_logging() setup
    # (called just before this, in run_live.py) isn't silently clobbered.
    root = logging.getLogger()
    saved_level = root.level
    saved_handlers = list(root.handlers)

    config = Config(_ALEMBIC_INI)
    command.upgrade(config, "head")

    root.setLevel(saved_level)
    root.handlers = saved_handlers
