# core/domain/charges.py
"""Intraday equity trading charges — brokerage + statutory taxes/fees — so
realized P&L reflects what actually lands in the account, not just the raw
entry/exit price difference PaperBroker computes (see runners/paper_trading/
paper_broker.py). Modeled on Zerodha's published intraday equity charge
structure, since that's the broker this app trades against.

Rates are editable (core/application/interfaces/charge_config_repository.py
persists them, server/main.py exposes GET/PUT /api/settings/charges) — the
constants below are only the shipped defaults, matching Zerodha's rates as
of 2026.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.domain.enums import OrderSide


@dataclass(frozen=True)
class ChargeConfig:
    """One rate card. Every *_pct is a fraction (0.0003 == 0.03%), not a
    whole-number percent, so callers never need a stray /100 at the call
    site."""

    # Zerodha intraday equity: 0.03% of order value or ₹20, whichever is
    # lower — charged per executed order, so once on entry AND once on exit.
    brokerage_pct: float = 0.0003
    brokerage_max_per_order: float = 20.0
    # Securities Transaction Tax: 0.025% of turnover, sell side only.
    stt_pct: float = 0.00025
    # NSE exchange transaction charges, both legs.
    exchange_txn_pct: float = 0.0000297
    # SEBI turnover fee (₹10/crore), both legs.
    sebi_pct: float = 0.000001
    # Stamp duty, buy side only.
    stamp_duty_pct: float = 0.00003
    # GST on (brokerage + exchange transaction charges).
    gst_pct: float = 0.18


def options_charge_config() -> ChargeConfig:
    """Zerodha F&O options rate card -- structurally different enough from
    equity intraday that reusing EQUITY_DEFAULTS would misprice every
    trade, but compute_charges()'s formula shape (min(turnover*pct, cap)
    brokerage, STT on sell turnover, exchange/SEBI both legs, stamp duty
    buy side, GST on brokerage+exchange) already fits options too -- only
    the rate constants differ, so this reuses ChargeConfig rather than a
    parallel dataclass.

    Public/best-effort defaults, same "editable, not gospel" status as
    EQUITY_DEFAULTS (see module docstring) -- verify against Zerodha's
    current published rates before trusting exact net P&L figures, since
    STT on options has been revised more than once by the government
    (this reflects the post-Oct-2024 hike).

    brokerage_pct=1.0 is a deliberate trick, not a real percentage: real
    options brokerage is a flat Rs 20/executed-order with no turnover
    comparison at all (unlike equity's genuine "0.03% or Rs20, whichever
    is lower"). Setting the pct absurdly high guarantees compute_charges's
    min(turnover*pct, cap) always resolves to the cap, i.e. flat Rs 20,
    without needing a second code path.
    """
    return ChargeConfig(
        brokerage_pct=1.0,
        brokerage_max_per_order=20.0,
        # STT: 0.1% of premium, sell side only (post-Oct-2024 rate).
        stt_pct=0.001,
        # NSE options exchange transaction charge -- far higher than
        # equity's 0.00297% since it's levied on the (small) premium, not
        # notional value.
        exchange_txn_pct=0.0003503,
        sebi_pct=0.000001,
        stamp_duty_pct=0.00003,
        gst_pct=0.18,
    )


@dataclass(frozen=True)
class ChargeBreakdown:
    brokerage: float
    stt: float
    exchange_txn: float
    sebi: float
    stamp_duty: float
    gst: float

    @property
    def total(self) -> float:
        return self.brokerage + self.stt + self.exchange_txn + self.sebi + self.stamp_duty + self.gst


def compute_charges(
    entry_price: float,
    exit_price: float,
    quantity: int,
    side: OrderSide,
    config: ChargeConfig,
) -> ChargeBreakdown:
    """Round-trip charges for one closed trade. `side` is the entry side —
    a BUY trade's buy leg is the entry and sell leg is the exit; a SELL
    (short) trade is the reverse."""

    entry_turnover = entry_price * quantity
    exit_turnover = exit_price * quantity

    if side == OrderSide.BUY:
        buy_turnover, sell_turnover = entry_turnover, exit_turnover
    else:
        buy_turnover, sell_turnover = exit_turnover, entry_turnover

    brokerage = (
        min(entry_turnover * config.brokerage_pct, config.brokerage_max_per_order)
        + min(exit_turnover * config.brokerage_pct, config.brokerage_max_per_order)
    )
    stt = sell_turnover * config.stt_pct
    exchange_txn = (entry_turnover + exit_turnover) * config.exchange_txn_pct
    sebi = (entry_turnover + exit_turnover) * config.sebi_pct
    stamp_duty = buy_turnover * config.stamp_duty_pct
    gst = (brokerage + exchange_txn) * config.gst_pct

    return ChargeBreakdown(
        brokerage=brokerage,
        stt=stt,
        exchange_txn=exchange_txn,
        sebi=sebi,
        stamp_duty=stamp_duty,
        gst=gst,
    )
