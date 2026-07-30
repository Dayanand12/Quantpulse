"""add timeframe to deployments

Revision ID: 5ec2b0d068f0
Revises: 5f678bcbcdfa
Create Date: 2026-07-30 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ec2b0d068f0'
down_revision: Union[str, Sequence[str], None] = '5f678bcbcdfa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Backfill existing deployments to "minute" (1-minute) — the bar size
    # every deployment was implicitly using before this became
    # configurable (see live/live_engine.py::SUPPORTED_TIMEFRAMES).
    op.add_column(
        'deployments',
        sa.Column('timeframe', sa.String(length=10), nullable=False, server_default='minute'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('deployments', 'timeframe')
