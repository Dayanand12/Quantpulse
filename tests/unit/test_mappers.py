import datetime as dt

from infrastructure.trading.mappers import trade_from_raw


def _raw_trade(**overrides):
    raw = dict(
        symbol="RELIANCE",
        side="SELL",
        qty=50,
        entry=250.0,
        exit=244.0,
        pnl=300.0,
        closed_at=dt.datetime(2026, 1, 1, 9, 30),
    )
    raw.update(overrides)
    return raw


def test_trade_from_raw_maps_market_snapshot_into_entry_fields():
    snapshot = {"ltp": 250.0, "rsi": 28.0, "adx": 31.0, "atr_pct": 1.2, "vwap": 248.0, "volume_ratio": 2.0}

    trade = trade_from_raw(_raw_trade(market_snapshot=snapshot))

    assert trade.entry_rsi == 28.0
    assert trade.entry_adx == 31.0
    assert trade.entry_atr_pct == 1.2
    assert trade.entry_vwap == 248.0
    assert trade.entry_volume_ratio == 2.0
    assert trade.market_condition == "Trending / High Volume / Above VWAP"


def test_trade_from_raw_leaves_market_fields_none_without_a_snapshot():
    trade = trade_from_raw(_raw_trade())

    assert trade.entry_rsi is None
    assert trade.entry_adx is None
    assert trade.entry_atr_pct is None
    assert trade.entry_vwap is None
    assert trade.entry_volume_ratio is None
    assert trade.market_condition is None
