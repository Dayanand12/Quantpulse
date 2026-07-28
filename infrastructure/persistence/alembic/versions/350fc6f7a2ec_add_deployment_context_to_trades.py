"""add deployment context to trades

Revision ID: 350fc6f7a2ec
Revises: 9f5429c44037
Create Date: 2026-07-28 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '350fc6f7a2ec'
down_revision: Union[str, Sequence[str], None] = '9f5429c44037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('trades', sa.Column('initial_stop_loss', sa.Float(), nullable=True))
    op.add_column('trades', sa.Column('deployment_id', sa.String(length=32), nullable=True))
    op.add_column('trades', sa.Column('strategy_name', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_trades_deployment_id'), 'trades', ['deployment_id'], unique=False)
    op.create_index(op.f('ix_trades_closed_at'), 'trades', ['closed_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_trades_closed_at'), table_name='trades')
    op.drop_index(op.f('ix_trades_deployment_id'), table_name='trades')
    op.drop_column('trades', 'strategy_name')
    op.drop_column('trades', 'deployment_id')
    op.drop_column('trades', 'initial_stop_loss')
