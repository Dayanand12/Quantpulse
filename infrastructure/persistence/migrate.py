"""Programmatic `alembic upgrade head`.

Called once at process startup (run_live.py) so the SQLite schema is always
current without a manual migration step — reasonable for a single-instance
local app; a multi-instance/cloud deployment would run this as a separate
release step instead of at every process start.
"""

import os

from alembic import command
from alembic.config import Config

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ALEMBIC_INI = os.path.join(_PROJECT_ROOT, "alembic.ini")


def run_migrations() -> None:
    config = Config(_ALEMBIC_INI)
    command.upgrade(config, "head")
