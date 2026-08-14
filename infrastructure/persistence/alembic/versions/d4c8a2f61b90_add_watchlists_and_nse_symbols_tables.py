"""add watchlists table for multiple named watchlists, and nse_symbols for autocomplete

Revision ID: d4c8a2f61b90
Revises: 7a2e1c9b4f68
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4c8a2f61b90'
down_revision: Union[str, Sequence[str], None] = '7a2e1c9b4f68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'watchlists',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('name', name='uq_watchlists_name'),
    )

    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO watchlists (name, created_at) VALUES ('Default', CURRENT_TIMESTAMP)"
    ))
    default_id = conn.execute(sa.text("SELECT id FROM watchlists WHERE name = 'Default'")).scalar()

    # SQLite can't ALTER the existing `symbol` column's unique=True
    # constraint directly — it has no name to target (unlike the previous
    # migration's uq_backtest_results_identity, which was explicitly
    # named). Rename, recreate with the final shape, copy data across, drop
    # the old table — every pre-existing symbol becomes part of the new
    # "Default" watchlist, so nothing already saved is lost.
    op.rename_table('watchlist_symbols', 'watchlist_symbols_old')
    op.create_table(
        'watchlist_symbols',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('watchlist_id', sa.Integer(), sa.ForeignKey('watchlists.id'), nullable=False),
        sa.Column('symbol', sa.String(length=32), nullable=False),
        sa.UniqueConstraint('watchlist_id', 'symbol', name='uq_watchlist_symbols_watchlist_id_symbol'),
    )
    conn.execute(sa.text(
        "INSERT INTO watchlist_symbols (watchlist_id, symbol) "
        "SELECT :wid, symbol FROM watchlist_symbols_old"
    ), {"wid": default_id})
    op.drop_table('watchlist_symbols_old')

    # NSE equity symbol master, for typeahead suggestions while adding a
    # symbol to a watchlist — resynced on demand from Kite's instrument
    # dump (POST /api/symbols/resync), not auto-refreshed, since new NSE
    # listings are rare enough that a manual trigger is fine.
    op.create_table(
        'nse_symbols',
        sa.Column('tradingsymbol', sa.String(length=32), primary_key=True),
        sa.Column('name', sa.String(length=128), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('nse_symbols')

    op.rename_table('watchlist_symbols', 'watchlist_symbols_new')
    op.create_table(
        'watchlist_symbols',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(length=32), nullable=False, unique=True),
    )
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO watchlist_symbols (symbol) SELECT DISTINCT symbol FROM watchlist_symbols_new"
    ))
    op.drop_table('watchlist_symbols_new')

    op.drop_table('watchlists')
