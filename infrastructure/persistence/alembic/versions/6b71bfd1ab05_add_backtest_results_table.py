"""add backtest_results table

Revision ID: 6b71bfd1ab05
Revises: c8f3a1d9e5b7
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b71bfd1ab05'
down_revision: Union[str, Sequence[str], None] = 'c8f3a1d9e5b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Unique constraint must be declared inline in create_table on SQLite —
    # ALTER TABLE ADD CONSTRAINT isn't supported by the SQLite dialect (no
    # native ALTER for constraints; alembic's batch mode copy-and-move
    # workaround is overkill for a brand new table with no existing rows).
    op.create_table(
        'backtest_results',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('strategy_name', sa.String(length=64), nullable=False),
        sa.Column('symbols', sa.Text(), nullable=False),
        sa.Column('timeframe', sa.String(length=10), nullable=False),
        sa.Column('date_from', sa.Date(), nullable=False),
        sa.Column('date_to', sa.Date(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('stoploss_pct', sa.Float(), nullable=False),
        sa.Column('target_pct', sa.Float(), nullable=False),
        sa.Column('trailing_pct', sa.Float(), nullable=False),
        sa.Column('max_cycles_per_day', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.String(length=5), nullable=False),
        sa.Column('end_time', sa.String(length=5), nullable=False),
        sa.Column('charges_enabled', sa.Boolean(), nullable=False),
        sa.Column('result_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            'strategy_name', 'symbols', 'timeframe', 'date_from', 'date_to',
            'quantity', 'stoploss_pct', 'target_pct', 'trailing_pct',
            'max_cycles_per_day', 'start_time', 'end_time', 'charges_enabled',
            name='uq_backtest_results_identity',
        ),
    )
    op.create_index('ix_backtest_results_strategy_name', 'backtest_results', ['strategy_name'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('backtest_results')
