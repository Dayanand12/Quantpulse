"""add strategy_params_json to backtest_results identity

Revision ID: 5739ff674158
Revises: 6b71bfd1ab05
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5739ff674158'
down_revision: Union[str, Sequence[str], None] = '6b71bfd1ab05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite can't ALTER a unique constraint directly (confirmed the hard
    # way on the previous migration) — batch mode does the copy-and-move
    # dance for us, preserving existing rows (backfilled with "" for the
    # new column, meaning "no condition-JSON was in use for this run",
    # which is factually correct for every row created before this
    # feature existed).
    with op.batch_alter_table('backtest_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column('strategy_params_json', sa.Text(), nullable=False, server_default=''))
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
            ],
        )
        batch_op.drop_column('strategy_params_json')
