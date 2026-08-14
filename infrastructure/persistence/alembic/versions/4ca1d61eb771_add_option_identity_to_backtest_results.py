"""add option identity columns to backtest_results

Revision ID: 4ca1d61eb771
Revises: f1348dcae8a3
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ca1d61eb771'
down_revision: Union[str, Sequence[str], None] = 'f1348dcae8a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('backtest_results', sa.Column('option_underlying', sa.String(length=32), nullable=True))
    op.add_column('backtest_results', sa.Column('option_strike', sa.Float(), nullable=True))
    op.add_column('backtest_results', sa.Column('option_expiry', sa.Date(), nullable=True))
    op.add_column('backtest_results', sa.Column('option_side', sa.String(length=2), nullable=True))
    op.create_index('ix_backtest_results_option_underlying', 'backtest_results', ['option_underlying'])

    # Backfill existing rows (983 as of this migration) whose `symbols`
    # already matches OptionContract.symbol's shape
    # ("UNDERLYING:STRIKEsSIDE:EXPIRY") — inlined here rather than
    # importing core.domain.models.OptionContract, since a migration
    # should stay correct even if that class's format ever changes later.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, symbols FROM backtest_results WHERE symbols LIKE '%:%:%'")).fetchall()
    for row_id, symbols in rows:
        parts = symbols.split(":")
        if len(parts) != 3:
            continue
        underlying, strike_side, expiry = parts
        side = strike_side[-2:]
        if side not in ("CE", "PE"):
            continue
        try:
            strike = float(strike_side[:-2])
        except ValueError:
            continue
        conn.execute(
            sa.text(
                "UPDATE backtest_results SET option_underlying=:u, option_strike=:s, "
                "option_expiry=:e, option_side=:side WHERE id=:id"
            ),
            {"u": underlying, "s": strike, "e": expiry, "side": side, "id": row_id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_backtest_results_option_underlying', table_name='backtest_results')
    op.drop_column('backtest_results', 'option_side')
    op.drop_column('backtest_results', 'option_expiry')
    op.drop_column('backtest_results', 'option_strike')
    op.drop_column('backtest_results', 'option_underlying')
