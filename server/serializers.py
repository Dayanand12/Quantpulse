"""Domain -> wire-format mapping for the REST/WebSocket API.

This is the API layer's actual job under Clean Architecture: translate
domain objects into whatever shape a client needs, so domain code never
needs to know it's being consumed by a REST API, a WebSocket, or (later) a
desktop/mobile client. Field names here intentionally match the existing
frontend TypeScript types (qty/entry/exit, not quantity/entry_price/
exit_price) so the React app didn't need to change when the backend moved
to a domain model with clearer internal names.
"""

from typing import Dict

from core.domain.models import MarketSnapshot, Position, Trade


def position_to_dict(position: Position) -> dict:
    return {
        "side": position.side.value,
        "qty": position.quantity,
        "entry": position.entry_price,
    }


def trade_to_dict(trade: Trade) -> dict:
    return {
        "symbol": trade.symbol,
        "entry": trade.entry_price,
        "exit": trade.exit_price,
        "side": trade.side.value,
        "qty": trade.quantity,
        "pnl": trade.pnl,
        "deployment_id": trade.deployment_id,
        "strategy_name": trade.strategy_name,
    }


def snapshot_to_dict(snapshot: MarketSnapshot) -> dict:
    return {
        "ltp": snapshot.ltp,
        "ema5": snapshot.ema5,
        "ema9": snapshot.ema9,
        "ema21": snapshot.ema21,
        "rsi": snapshot.rsi,
        "adx": snapshot.adx,
        "atr_pct": snapshot.atr_pct,
        "vwap": snapshot.vwap,
        "volume_ratio": snapshot.volume_ratio,
        "orb_low": snapshot.orb_low,
        "distance_to_or_low": snapshot.distance_to_or_low,
    }


def snapshot_map_to_dict(snapshot_map: Dict[str, MarketSnapshot]) -> dict:
    return {symbol: snapshot_to_dict(s) for symbol, s in snapshot_map.items()}
