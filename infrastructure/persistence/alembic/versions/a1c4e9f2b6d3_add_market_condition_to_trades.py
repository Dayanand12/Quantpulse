"""add market condition to trades

Revision ID: a1c4e9f2b6d3
Revises: 5ec2b0d068f0
Create Date: 2026-08-03 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4e9f2b6d3'
down_revision: Union[str, Sequence[str], None] = '5ec2b0d068f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('trades', sa.Column('entry_rsi', sa.Float(), nullable=True))
    op.add_column('trades', sa.Column('entry_adx', sa.Float(), nullable=True))
    op.add_column('trades', sa.Column('entry_atr_pct', sa.Float(), nullable=True))
    op.add_column('trades', sa.Column('entry_vwap', sa.Float(), nullable=True))
    op.add_column('trades', sa.Column('entry_volume_ratio', sa.Float(), nullable=True))
    op.add_column('trades', sa.Column('market_condition', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('trades', 'market_condition')
    op.drop_column('trades', 'entry_volume_ratio')
    op.drop_column('trades', 'entry_vwap')
    op.drop_column('trades', 'entry_atr_pct')
    op.drop_column('trades', 'entry_adx')
    op.drop_column('trades', 'entry_rsi')
