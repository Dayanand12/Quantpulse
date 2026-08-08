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
