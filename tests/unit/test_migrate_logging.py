import logging
from unittest.mock import patch

from infrastructure.persistence import migrate


def test_run_migrations_restores_root_logging_config_after_alembic_resets_it():
    # infrastructure/persistence/alembic/env.py runs logging.config.
    # fileConfig(alembic.ini) as a side effect of command.upgrade(),
    # which resets the root logger's level/handlers globally (not scoped
    # to alembic's own loggers). Simulate exactly that side effect via a
    # fake upgrade, and confirm run_migrations() undoes it.
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level

    sentinel_handler = logging.StreamHandler()
    root.handlers = [sentinel_handler]
    root.setLevel(logging.INFO)

    def fake_upgrade(config, revision):
        root.setLevel(logging.WARNING)
        root.handlers = []

    try:
        with patch.object(migrate.command, "upgrade", fake_upgrade):
            migrate.run_migrations()

        assert root.level == logging.INFO
        assert root.handlers == [sentinel_handler]
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)
