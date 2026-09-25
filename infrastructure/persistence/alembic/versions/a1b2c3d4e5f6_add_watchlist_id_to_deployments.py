"""add watchlist_id to deployments

Revision ID: a1b2c3d4e5f6
Revises: 250870608b8a
Create Date: 2026-09-15 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '250870608b8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NULL for every existing row — classic fixed-symbols_json mode,
    # unchanged. Only a deployment explicitly switched to watchlist-bound
    # mode (core/domain/models.py::Deployment docstring) gets this set.
    op.add_column(
        'deployments',
        sa.Column('watchlist_id', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('deployments', 'watchlist_id')
