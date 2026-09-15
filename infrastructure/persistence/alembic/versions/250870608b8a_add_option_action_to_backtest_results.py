"""add option_action to backtest_results identity

Revision ID: 250870608b8a
Revises: 7e2b9c1f4a03
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '250870608b8a'
down_revision: Union[str, Sequence[str], None] = '7e2b9c1f4a03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Same batch-mode add-column-then-recreate-unique-constraint dance as
    # the strategy_params_json migration (5739ff674158) — SQLite can't
    # ALTER a unique constraint directly. Existing rows backfill "" (no
    # run before this feature ever overrode the strategy's own side, so
    # "" — meaning "not specified" — is factually correct for all of them).
    with op.batch_alter_table('backtest_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column('option_action', sa.Text(), nullable=False, server_default=''))
        batch_op.drop_constraint('uq_backtest_results_identity', type_='unique')
        batch_op.create_unique_constraint(
            'uq_backtest_results_identity',
            [
                'strategy_name', 'symbols', 'timeframe', 'date_from', 'date_to',
                'quantity', 'stoploss_pct', 'target_pct', 'trailing_pct',
                'max_cycles_per_day', 'start_time', 'end_time', 'charges_enabled',
                'strategy_params_json', 'option_action',
            ],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('backtest_results', schema=None) as batch_op:
        batch_op.drop_constraint('uq_backtest_results_identity', type_='unique')
        batch_op.create_unique_constraint(
            'uq_backtest_results_identity',
            [
                'strategy_name', 'symbols', 'timeframe', 'date_from', 'date_to',
                'quantity', 'stoploss_pct', 'target_pct', 'trailing_pct',
                'max_cycles_per_day', 'start_time', 'end_time', 'charges_enabled',
                'strategy_params_json',
            ],
        )
        batch_op.drop_column('option_action')
