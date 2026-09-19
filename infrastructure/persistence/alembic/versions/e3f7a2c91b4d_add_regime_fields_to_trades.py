"""add regime fields to trades

Revision ID: e3f7a2c91b4d
Revises: a1b2c3d4e5f6
Create Date: 2026-09-19 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f7a2c91b4d'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # entry_oi has existed on core.domain.models.Trade since a1c4e9f2b6d3
    # but was never actually given a column — every trade silently
    # dropped it on save. Backfilling the column now, alongside the new
    # regime fields, closes that gap.
    op.add_column('trades', sa.Column('entry_oi', sa.Float(), nullable=True))
    op.add_column('trades', sa.Column('regime_trend', sa.String(length=32), nullable=True))
    op.add_column('trades', sa.Column('regime_volatility', sa.String(length=32), nullable=True))
    op.add_column('trades', sa.Column('index_trend', sa.String(length=32), nullable=True))
    op.add_column('trades', sa.Column('vix_bucket', sa.String(length=16), nullable=True))
    op.add_column('trades', sa.Column('session_phase', sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('trades', 'session_phase')
    op.drop_column('trades', 'vix_bucket')
    op.drop_column('trades', 'index_trend')
    op.drop_column('trades', 'regime_volatility')
    op.drop_column('trades', 'regime_trend')
    op.drop_column('trades', 'entry_oi')
