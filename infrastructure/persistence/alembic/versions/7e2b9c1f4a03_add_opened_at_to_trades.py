"""add opened_at to trades

Revision ID: 7e2b9c1f4a03
Revises: 4ca1d61eb771
Create Date: 2026-08-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e2b9c1f4a03'
down_revision: Union[str, Sequence[str], None] = '4ca1d61eb771'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Entry timestamp — never captured before this migration (see
    # PaperBroker.enter()), so every existing row stays NULL; only trades
    # closed after this ships have a real value.
    op.add_column('trades', sa.Column('opened_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('trades', 'opened_at')
