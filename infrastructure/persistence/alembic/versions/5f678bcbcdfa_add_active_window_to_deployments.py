"""add active window to deployments

Revision ID: 5f678bcbcdfa
Revises: 350fc6f7a2ec
Create Date: 2026-07-29 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f678bcbcdfa'
down_revision: Union[str, Sequence[str], None] = '350fc6f7a2ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Backfill existing deployments with the window they were already
    # implicitly running under (see live/deployment_runner.py, before this
    # became per-deployment) so nothing's behavior changes on migrate.
    op.add_column(
        'deployments',
        sa.Column('start_time', sa.String(length=5), nullable=False, server_default='09:20'),
    )
    op.add_column(
        'deployments',
        sa.Column('end_time', sa.String(length=5), nullable=False, server_default='11:30'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('deployments', 'end_time')
    op.drop_column('deployments', 'start_time')
