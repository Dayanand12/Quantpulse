"""add regime_calls table

Revision ID: b78ebb81630f
Revises: a1c4e9f2b6d3
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b78ebb81630f'
down_revision: Union[str, Sequence[str], None] = 'a1c4e9f2b6d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'regime_calls',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(length=32), nullable=False),
        sa.Column('logged_at', sa.DateTime(), nullable=False),
        sa.Column('ltp', sa.Float(), nullable=False),
        sa.Column('regime', sa.String(length=32), nullable=False),
        sa.Column('trend_strength', sa.String(length=16), nullable=False),
        sa.Column('volatility_state', sa.String(length=16), nullable=False),
        sa.Column('confidence_score', sa.Integer(), nullable=False),
        sa.Column('decision', sa.String(length=32), nullable=False),
        sa.Column('suggested_side', sa.String(length=8), nullable=True),
        sa.Column('return_15m', sa.Float(), nullable=True),
        sa.Column('return_30m', sa.Float(), nullable=True),
        sa.Column('return_60m', sa.Float(), nullable=True),
        sa.UniqueConstraint('symbol', 'logged_at', name='uq_regime_calls_symbol_logged_at'),
    )
    op.create_index('ix_regime_calls_symbol', 'regime_calls', ['symbol'])
    op.create_index('ix_regime_calls_logged_at', 'regime_calls', ['logged_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_regime_calls_logged_at', table_name='regime_calls')
    op.drop_index('ix_regime_calls_symbol', table_name='regime_calls')
    op.drop_table('regime_calls')
