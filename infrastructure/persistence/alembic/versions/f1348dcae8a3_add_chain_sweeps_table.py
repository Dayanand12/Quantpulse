"""add chain_sweeps table

Revision ID: f1348dcae8a3
Revises: d4c8a2f61b90
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1348dcae8a3'
down_revision: Union[str, Sequence[str], None] = 'd4c8a2f61b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'chain_sweeps',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('strategy_name', sa.String(length=64), nullable=False),
        sa.Column('underlying', sa.String(length=32), nullable=False),
        sa.Column('category', sa.String(length=16), nullable=False),
        sa.Column('expiry_filter', sa.String(length=16), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('shared_config_json', sa.Text(), nullable=False),
        sa.Column('contracts_json', sa.Text(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_chain_sweeps_strategy_name', 'chain_sweeps', ['strategy_name'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('chain_sweeps')
