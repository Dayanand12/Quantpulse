"""add charges to trades and charge_config table

Revision ID: c8f3a1d9e5b7
Revises: b78ebb81630f
Create Date: 2026-08-06 20:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from core.domain.charges import ChargeConfig, compute_charges
from core.domain.enums import OrderSide


# revision identifiers, used by Alembic.
revision: str = 'c8f3a1d9e5b7'
down_revision: Union[str, Sequence[str], None] = 'b78ebb81630f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('trades', sa.Column('charges', sa.Float(), nullable=True))
    op.add_column('trades', sa.Column('net_pnl', sa.Float(), nullable=True))

    op.create_table(
        'charge_config',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('brokerage_pct', sa.Float(), nullable=False),
        sa.Column('brokerage_max_per_order', sa.Float(), nullable=False),
        sa.Column('stt_pct', sa.Float(), nullable=False),
        sa.Column('exchange_txn_pct', sa.Float(), nullable=False),
        sa.Column('sebi_pct', sa.Float(), nullable=False),
        sa.Column('stamp_duty_pct', sa.Float(), nullable=False),
        sa.Column('gst_pct', sa.Float(), nullable=False),
    )

    default_config = ChargeConfig()
    charge_config_table = sa.table(
        'charge_config',
        sa.column('id', sa.Integer),
        sa.column('brokerage_pct', sa.Float),
        sa.column('brokerage_max_per_order', sa.Float),
        sa.column('stt_pct', sa.Float),
        sa.column('exchange_txn_pct', sa.Float),
        sa.column('sebi_pct', sa.Float),
        sa.column('stamp_duty_pct', sa.Float),
        sa.column('gst_pct', sa.Float),
    )
    op.bulk_insert(charge_config_table, [{
        'id': 1,
        'brokerage_pct': default_config.brokerage_pct,
        'brokerage_max_per_order': default_config.brokerage_max_per_order,
        'stt_pct': default_config.stt_pct,
        'exchange_txn_pct': default_config.exchange_txn_pct,
        'sebi_pct': default_config.sebi_pct,
        'stamp_duty_pct': default_config.stamp_duty_pct,
        'gst_pct': default_config.gst_pct,
    }])

    # Backfill: every trade closed before this migration gets charges
    # computed retroactively with the default rate card, so realized P&L
    # (core/domain/metrics.py) is consistent across old and new trades
    # instead of treating pre-migration trades as charge-free.
    bind = op.get_bind()
    trades_table = sa.table(
        'trades',
        sa.column('id', sa.Integer),
        sa.column('side', sa.String),
        sa.column('quantity', sa.Integer),
        sa.column('entry_price', sa.Float),
        sa.column('exit_price', sa.Float),
        sa.column('pnl', sa.Float),
        sa.column('charges', sa.Float),
        sa.column('net_pnl', sa.Float),
    )

    rows = bind.execute(
        sa.select(
            trades_table.c.id,
            trades_table.c.side,
            trades_table.c.quantity,
            trades_table.c.entry_price,
            trades_table.c.exit_price,
            trades_table.c.pnl,
        )
    ).fetchall()

    for row in rows:
        breakdown = compute_charges(
            entry_price=row.entry_price,
            exit_price=row.exit_price,
            quantity=row.quantity,
            side=OrderSide(row.side),
            config=default_config,
        )
        bind.execute(
            trades_table.update()
            .where(trades_table.c.id == row.id)
            .values(charges=breakdown.total, net_pnl=row.pnl - breakdown.total)
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('charge_config')
    op.drop_column('trades', 'net_pnl')
    op.drop_column('trades', 'charges')
