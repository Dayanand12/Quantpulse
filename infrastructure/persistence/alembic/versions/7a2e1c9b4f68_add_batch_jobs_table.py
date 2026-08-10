"""add batch_jobs table

Revision ID: 7a2e1c9b4f68
Revises: 5739ff674158
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a2e1c9b4f68'
down_revision: Union[str, Sequence[str], None] = '5739ff674158'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'batch_jobs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('strategy_name', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('shared_config_json', sa.Text(), nullable=False),
        sa.Column('scenarios_json', sa.Text(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_batch_jobs_strategy_name', 'batch_jobs', ['strategy_name'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('batch_jobs')
