"""Shared raw-dict -> domain mappers for PaperBroker-backed adapters.

Factored out so PaperOrderRepository and PaperPortfolioService don't
duplicate the same dict shape knowledge (PaperBroker still speaks plain
dicts — see live/paper_broker.py — this is the one place that translates
that shape into core.domain.models).
"""

from core.domain.enums import OrderSide
from core.domain.models import Position, RejectedEntry, Trade


def position_from_raw(symbol: str, raw: dict) -> Position:
    return Position(
        symbol=symbol,
        side=OrderSide(raw["side"]),
        quantity=raw["qty"],
        entry_price=raw["entry"],
    )


def trade_from_raw(raw: dict) -> Trade:
    kwargs = dict(
        symbol=raw["symbol"],
        side=OrderSide(raw["side"]),
        quantity=raw["qty"],
        entry_price=raw["entry"],
        exit_price=raw["exit"],
        pnl=raw["pnl"],
        initial_stop_loss=raw.get("initial_stop_loss"),
    )
    # Trades logged before this field existed have no "closed_at" key —
    # let Trade's own default_factory (datetime.now) fill it in rather
    # than claiming a false precise time for old data.
    if "closed_at" in raw:
        kwargs["closed_at"] = raw["closed_at"]
    return Trade(**kwargs)


def rejected_entry_from_raw(raw: dict) -> RejectedEntry:
    return RejectedEntry(
        symbol=raw["symbol"],
        side=OrderSide(raw["side"]),
        quantity=raw["quantity"],
        price=raw["price"],
        required_capital=raw["required_capital"],
        available_capital=raw["available_capital"],
        reason=raw["reason"],
        at=raw["at"],
    )
